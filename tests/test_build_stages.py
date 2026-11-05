import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from integration import build
from integration.build_policy import bound_workers, partition_policy, stream_lz4, zip_policy
from integration.debloat import PARTITIONS, plan
from integration.kernel_budget import bounded
from integration.package_inputs import capture, identifier, retire, check_image
from integration.firmware_check import inspect as inspect_firmware
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('staged_prepare', ROOT / 'scripts/prepare_workspace.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def fixture(root):
    (root / 'out').mkdir()
    (root / 'BEYOUD-WORKSPACE.json').write_text(json.dumps(dict(target='SM-G975F', codename='beyond2lte')))
    (root / 'out/config.sh').write_text('SOURCE_FIRMWARE="SM-S926B/EUX"\nTARGET_FIRMWARE="SM-G975F/AUT"\nSOURCE_API_LEVEL="37"\nTARGET_API_LEVEL="31"\nSOURCE_HAS_SYSTEM_EXT="true"\n')
    records = [dict(model=model, csc=csc, version='A/B/C/D', size=100)
               for model, csc in [('SM-S926B', 'EUX'), ('SM-G975F', 'AUT')]]
    (root / 'out/firmware-lock.json').write_text(json.dumps(dict(schema_version=1, firmwares=records)))


def firmware(root):
    for pair, name in [('SM-S926B_EUX', 'e2s'), ('SM-G975F_AUT', 'beyond2lte')]:
        base = root / 'out/fw' / pair
        (base / 'system/system').mkdir(parents=True, exist_ok=True)
        (base / 'vendor').mkdir(exist_ok=True)
        if pair.startswith('SM-S926B'):
            (base / 'system_ext').mkdir(exist_ok=True)
        (base / 'os_partitions_metadata.txt').write_text('system_size=100000000000\nvendor_size=100000000000\n')
        (base / '.extracted').write_text('A/B/C/D')
        (base / 'system/system/build.prop').write_text(f'ro.build.product={name}\nro.build.version.sdk={37 if pair.startswith("SM-S926B") else 31}\n')
        (base / 'vendor/build.prop').write_text(f'ro.product.vendor.device={name}xx\n')


class StageTests(unittest.TestCase):
    def test_workflow_keeps_one_complete_rom_and_separate_firmware_stages(self):
        text = (ROOT / '.github/workflows/alpha.yml').read_text()
        self.assertNotIn('split -b', text)
        self.assertNotIn('.part.', text)
        self.assertNotIn('samsunggithub/oneui85-lab', text)
        stages = ['dependencies', 'source', 'target', 'patch', 'retire', 'package']
        positions = [text.index(f'build_candidate.sh "$WORKSPACE" {stage}') for stage in stages]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('collect_alpha.py', text)
        self.assertIn('compression-level: 0', text)

    def test_actual_pinned_scripts_transform_and_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'reference/build', root, dirs_exist_ok=True)
            prepare.patch_downloader(root)
            prepare.patch_firmware_lookup(root)
            prepare.patch_parallel_builds(root)
            prepare.patch_sequential_firmwares(root)
            prepare.apply_build_policy(root)
            for path in root.rglob('*.sh'):
                subprocess.run(['bash', '-n', str(path)], check=True)
            text = (root / 'scripts/extract_fw.sh').read_text()
            self.assertLess(text.index('BEYOUD_UNPACK_PARTITION "${p}.img"'), text.index('rm -f "$FW_DIR/${MODEL}_${CSC}/super.img"'))
            self.assertNotIn('cleanup.sh" fw kernel', (root / 'scripts/make_rom.sh').read_text())
            self.assertIn('BEYOUD_COMPRESS_PARTITION "$TMP_DIR/$PARTITION.img"', (root / 'scripts/internal/build_flashable_zip.sh').read_text())
            self.assertIn('set -o pipefail', (root / 'scripts/utils/firmware_utils.sh').read_text())

    def test_apktool_uses_one_decode_pass_and_per_dex_api_metadata(self):
        script = ROOT / 'reference/build/scripts/apktool.sh'
        text = script.read_text()
        subprocess.run(['bash', '-n', str(script)], check=True)
        self.assertIn('dex_api_versions.tsv', text)
        self.assertIn('DEX_API_LEVEL=36', text)
        self.assertIn('BEYOUD_JOBS', text)
        self.assertNotIn('baksmali d -a 36 --ac false --di false', text)

    def test_super_partitions_are_unpacked_and_released_before_next_image(self):
        text = partition_policy((ROOT / 'reference/build/scripts/extract_fw.sh').read_text())
        functions = text[text.index('BEYOUD_UNPACK_PARTITION()'):text.index('GET_IMAGE_FILE_SYSTEM()')]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fw = root / 'fw/SM-S926B_EUX'
            fw.mkdir(parents=True)
            harness = functions + r'''
LOG_STEP_IN() { :; }; LOG_STEP_OUT() { :; }; LOG() { :; }
FILE_EXISTS_IN_TAR() { [[ "$2" == super.img ]]; }
EXTRACT_FILE_FROM_TAR() { printf super > "$FW_DIR/${MODEL}_${CSC}/super.img"; }
UNSPARSE_IMAGE() { :; }
STORE_OS_PARTITION_METADATA() { printf 'partition_list=system vendor product\n' > "$FW_DIR/${MODEL}_${CSC}/os_partitions_metadata.txt"; }
EVAL() { eval "$1"; }
lpunpack() {
  [[ -f "$3" ]] || return 70
  [[ ! -f "$4/system.img" && ! -f "$4/vendor.img" && ! -f "$4/product.img" ]] || return 71
  printf '%s' "$2" > "$4/$2.img"
}
BEYOUD_UNPACK_PARTITION() {
  [[ -f "$FW_DIR/${MODEL}_${CSC}/$1" ]] || return 0
  mkdir -p "$FW_DIR/${MODEL}_${CSC}/${1%.img}"
  cp "$FW_DIR/${MODEL}_${CSC}/$1" "$FW_DIR/${MODEL}_${CSC}/${1%.img}/content"
  rm "$FW_DIR/${MODEL}_${CSC}/$1"
}
EXTRACT_OS_PARTITIONS
'''
            script = root / 'extract.sh'
            script.write_text(harness)
            result = subprocess.run(['bash', str(script)], env=dict(os.environ, FW_DIR=str(root / 'fw'), MODEL='SM-S926B', CSC='EUX', AP_TAR='ap', CSC_TAR='csc'), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for partition in ('system', 'vendor', 'product'):
                self.assertEqual((fw / partition / 'content').read_text(), partition)
            self.assertFalse((fw / 'super.img').exists())
            self.assertFalse(list(fw.glob('*.img')))

    def test_worker_limit_and_earlier_failure_are_not_hidden(self):
        text = 'BEYOUD_PIDS=()\nfor i in 1 2; do\n (exit "$((i == 1 ? 7 : 0))") &\n BEYOUD_PIDS+=("$!")\ndone\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'workers.sh'
            path.write_text(bound_workers(text))
            result = subprocess.run(['bash', str(path)], env=dict(os.environ, BEYOUD_JOBS='1'))
            self.assertEqual(result.returncode, 1)

    def test_kernel_budget_does_not_modify_other_content(self):
        original = '# test\nCORES=`cat /proc/cpuinfo | grep -c processor`\necho "$CORES"\n'
        result = subprocess.run(['bash', '-c', bounded(original)], env=dict(os.environ, BEYOUD_JOBS='1'), capture_output=True, text=True)
        self.assertEqual(result.stdout, '1\n')
        with self.assertRaises(ValueError):
            bounded('different upstream schema')

    def test_runtime_failure_propagates_and_resource_samples_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            stream = io.StringIO()
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                build.run_command([sys.executable, '-c', 'raise SystemExit(7)'], Path(tmp), os.environ, stream, reserve=0, interval=.01)
            self.assertEqual(raised.exception.returncode, 7)
            self.assertIn('disk_free', stream.getvalue())

    def test_disk_guard_prevents_process_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'should-not-exist'
            with self.assertRaises(ValueError):
                build.run_command([sys.executable, '-c', f'open({str(path)!r},"w").close()'], Path(tmp), os.environ, io.StringIO(), reserve=10**30)
            self.assertFalse(path.exists())

    def test_package_identifiers_survive_verified_retirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            firmware(root)
            self.assertEqual(capture(root)['identifiers']['target_product'], 'beyond2lte')
            retire(root)
            self.assertFalse((root / 'out/fw').exists())
            self.assertEqual(identifier(root, 'source_vendor'), 'e2sxx')
            with self.assertRaises(ValueError):
                retire(root)
            lock = root / 'out/firmware-lock.json'
            lock.write_text(lock.read_text() + '\n')
            with self.assertRaises(ValueError):
                identifier(root, 'source_vendor')

    def test_actual_sdk_mismatch_blocks_patching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            firmware(root)
            inspect_firmware(root)
            p = root / 'out/fw/SM-S926B_EUX/system/system/build.prop'
            p.write_text(p.read_text().replace('sdk=37', 'sdk=36'))
            with self.assertRaises(ValueError):
                inspect_firmware(root)

    def test_sparse_logical_size_not_compressed_size_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            firmware(root)
            retire(root)
            image = root / 'image.img'
            # Tiny file, but a header declaring a huge expanded partition.
            image.write_bytes(struct.pack('<I4H4I', 0xED26FF3A, 1, 0, 28, 12, 4096, 100000000, 1, 0))
            with self.assertRaises(ValueError):
                check_image(root, 'system', image)
            image.write_bytes(b'raw')
            check_image(root, 'system', image)
            with self.assertRaises(ValueError):
                check_image(root, 'invented_partition', image)

    def test_retirement_rejects_unknown_directory_without_deleting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            firmware(root)
            (root / 'out/fw/personal').mkdir()
            with self.assertRaises(ValueError):
                retire(root)
            self.assertTrue((root / 'out/fw/SM-S926B_EUX/.extracted').is_file())
            self.assertFalse((root / 'out/beyoud-fw-retired.json').exists())

    def test_stages_resume_package_after_retirement_and_reject_recipe_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            def command(cmd, workspace, env, telemetry):
                if 'build_dependencies' in str(cmd):
                    tool = root / 'out/tools/bin/tool'
                    tool.parent.mkdir(parents=True)
                    tool.write_text('tool')
                elif 'stage.py' in str(cmd):
                    firmware(root)
                elif 'make_rom.sh' in str(cmd):
                    work = root / 'out/target/beyond2lte/work_dir'
                    work.mkdir(parents=True)
                    (work / '.completed').write_text('complete')
                elif 'build_flashable_zip' in str(cmd):
                    (root / 'out/ArtisanROM_alpha1_beyond2lte.zip').write_bytes(b'package')
                return 100
            with patch.object(build, 'environment', return_value={}), patch.object(build, 'run_command', side_effect=command), patch.object(build, 'package_budget', return_value={}):
                with self.assertRaises(ValueError):
                    build.execute(root, 'patch')
                for stage in ('dependencies', 'source', 'target', 'patch', 'retire', 'package'):
                    build.execute(root, stage)
                self.assertEqual(json.loads((root / 'out/beyoud-stages/package.json').read_text())['status'], 'success')
                # Output content, not merely presence of a checkpoint, is checked.
                (root / 'out/target/beyond2lte/work_dir/.completed').write_text('tampered')
                with self.assertRaises(ValueError):
                    build.execute(root, 'package')
                (root / 'out/target/beyond2lte/work_dir/.completed').write_text('complete')
                (root / 'buildenv.sh').write_text('recipe changed')
                with self.assertRaises(ValueError):
                    build.execute(root, 'package')

    def test_reference_recipe_changes_checkpoint_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            reference = root / 'reference/build/scripts'
            reference.mkdir(parents=True)
            recipe = reference / 'recipe.sh'
            recipe.write_text('version=1\\n')
            before = build.identity(root)
            recipe.write_text('version=2\\n')
            self.assertNotEqual(before, build.identity(root))

    def test_failed_stage_never_gets_success_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            with patch.object(build, 'environment', return_value={}), patch.object(build, 'run_command', side_effect=ValueError('synthetic failure')):
                with self.assertRaises(ValueError):
                    build.execute(root, 'dependencies')
            self.assertEqual(json.loads((root / 'out/beyoud-stages/dependencies.json').read_text())['status'], 'failed')

    def test_debloat_rejects_traversal_globs_and_essential_components(self):
        for value in ('../personal', '/system/bin/init', 'system/*', 'system/framework', 'system/priv-app/SecSettings'):
            values = [''] * len(PARTITIONS)
            values[2] = value
            with self.assertRaises(ValueError):
                plan(values)
        values = [''] * len(PARTITIONS)
        values[2] = 'system/priv-app/PetService\nsystem/priv-app/PetService\n'
        self.assertEqual(plan(values)['system'], ['system/priv-app/PetService'])

    def test_effective_historical_debloat_plan_is_allowed(self):
        source = ROOT / 'reference/build/unica/debloat.sh'
        platform = ROOT / 'reference/artisan-s10/platform/exynos9820/debloat.sh'
        command = 'SOURCE_IS_ESIM_SUPPORTED=true; TARGET_IS_ESIM_SUPPORTED=false; source "$1"; source "$2"; printf "%s\\0" "$ODM_DEBLOAT" "$PRODUCT_DEBLOAT" "$SYSTEM_DEBLOAT" "$SYSTEM_EXT_DEBLOAT" "$VENDOR_DEBLOAT" "$PRISM_DEBLOAT" "$OPTICS_DEBLOAT"'
        result = subprocess.run(['bash', '-c', command, 'test', str(source), str(platform)], check=True, capture_output=True)
        lists = result.stdout.decode().split('\0')[:-1]
        self.assertGreater(sum(map(len, plan(lists).values())), 0)
