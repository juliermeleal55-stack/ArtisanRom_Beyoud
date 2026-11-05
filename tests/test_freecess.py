from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from integration.freecess import adapt, apply
from integration.build_policy import debloat_workers
from integration.kernel_budget import bounded, harden_download, TOOLCHAIN_URL
from integration.patch_inventory import inventory
import os
from integration.framework_policy import install, PATCH, CUSTOMIZE

ROOT = Path(__file__).resolve().parents[1]


def smali(register='v2', opcode='const-string/jumbo', key='ro.product.model', args=None):
    return f'''.class public Lcom/android/server/am/FreecessController;
.super Ljava/lang/Object;
.method static constructor <clinit>()V
    .locals 8
    {opcode} {register}, "{key}"
    .line 123
    invoke-static {{{args or register}}}, Landroid/os/SystemProperties;->get(Ljava/lang/String;)Ljava/lang/String;
    move-result-object {register}
    return-void
.end method
'''


class FreecessTests(unittest.TestCase):
    def test_register_and_encoding_variations_preserve_all_other_code(self):
        for register, opcode in [('v2', 'const-string/jumbo'), ('v7', 'const-string'), ('p0', 'const-string')]:
            text = smali(register, opcode)
            result, status = adapt(text)
            self.assertEqual(result, text.replace('"ro.product.model"', '"ro.product.vendor.model"'))
            self.assertEqual(status, 'adapted')
            self.assertEqual(adapt(result), (result, 'already-adapted'))

    def test_range_invoke(self):
        text = smali(args='v2 .. v2').replace('invoke-static ', 'invoke-static/range ')
        self.assertEqual(adapt(text)[1], 'adapted')

    def test_ambiguous_unrelated_and_missing_reads_are_rejected(self):
        texts = [smali().replace('ro.product.model', 'unrelated'),
                 smali(args='v4'), smali() + smali(),
                 smali().replace('Landroid/os/SystemProperties;', 'Lother/Properties;')]
        for text in texts:
            with self.assertRaises(ValueError):
                adapt(text)

    def test_different_dex_location_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'smali_classes3/com/android/server/am/FreecessController.smali'
            path.parent.mkdir(parents=True)
            path.write_text(smali('v7', 'const-string'))
            apply(root)
            self.assertIn('ro.product.vendor.model', path.read_text())

    def test_optional_debloat_lists_do_not_fail_and_worker_errors_stop(self):
        original = (ROOT / 'reference/build/unica/patches/debloat/customize.sh').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts/utils').mkdir(parents=True)
            (root / 'scripts/utils/module_utils.sh').write_text('DELETE_FROM_WORK_DIR() { return "${TEST_DELETE_CODE:-0}"; }\n')
            code = debloat_workers(original)
            script = root / 'debloat.sh'
            script.write_text(code)
            env = dict(os.environ, SRC_DIR=str(root), OUT_DIR=str(root / 'out'), BEYOUD_JOBS='1')
            empty = subprocess.run(['bash', '-c', 'source "$1"', 'test', str(script)], env=env, capture_output=True, text=True)
            self.assertEqual(empty.returncode, 0, empty.stderr)
            failed = subprocess.run(['bash', '-c', 'source "$1"', 'test', str(script)], env=dict(env, SYSTEM_DEBLOAT='system/priv-app/PetService', TEST_DELETE_CODE='7'), capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)

    def test_toolchain_http_and_tar_failures_are_explicit(self):
        text = '#!/bin/bash\nCORES=`cat /proc/cpuinfo | grep -c processor`\ncurl -LJOk ' + TOOLCHAIN_URL + '\ntar xf main-clang-r547379.tar.gz\n'
        result = harden_download(bounded(text))
        self.assertNotIn('curl -LJOk', result)
        self.assertIn('curl --fail --location', result)
        self.assertIn('tar xf main-clang-r547379.tar.gz || exit 1', result)
        with self.assertRaises(ValueError):
            harden_download(text.replace('clang-r547379.tar.gz', 'different.tar.gz'))

    def test_inventory_distinguishes_disabled_modules_from_active_sites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('active', 'disabled'):
                path = root / 'unica/patches' / name
                path.mkdir(parents=True)
                (path / 'module.prop').write_text('name=Test')
                (path / 'customize.sh').write_text('HEX_PATCH binary old new || LOGW ignored')
            (root / 'unica/patches/disabled/disable').touch()
            report = inventory(root, 'beyond1lte', {})
            self.assertEqual(sum(not entry['disabled'] for entry in report['modules']), 1)
            self.assertTrue(report['modules'][0]['native_patch_scripts'])
            self.assertTrue(report['modules'][0]['ignored_failure_sites'])

    def test_failure_diagnostics_preserve_actual_smali_only_inside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / 'out/target/beyond1lte/apktool/services.jar/smali/FreecessController.smali'
            file.parent.mkdir(parents=True)
            file.write_text(smali())
            logs = root / 'out/beyoud-logs'
            logs.mkdir()
            (logs / 'patch.log').write_text(f'error: patch failed: {file}:193\n')
            subprocess.run(['python3', str(ROOT / 'scripts/annotate_build_failure.py'), str(root)], check=True, stdout=subprocess.PIPE)
            copies = list((logs / 'failed-smali').rglob('*.smali'))
            self.assertEqual(len(copies), 1)
            self.assertEqual(copies[0].read_bytes(), file.read_bytes())

    def test_installer_preserves_fix_and_refuses_unknown_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'reference/build', root, dirs_exist_ok=True)
            install(root)
            self.assertFalse((root / PATCH).exists())
            self.assertIn('DECODE_APK', (root / CUSTOMIZE).read_text())
            self.assertIn('freecess.py', (root / CUSTOMIZE).read_text())
            subprocess.run(['bash', '-n', str(root / CUSTOMIZE)], check=True)
            with self.assertRaises((ValueError, FileNotFoundError)):
                install(root)
