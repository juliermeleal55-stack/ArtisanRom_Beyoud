import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from integration.onerom.compat import donor_sdk, legacy_init
from integration.onerom.install import bluetooth_policy, install, verify, MODULES

ROOT = Path(__file__).resolve().parents[1]


class OneROMTests(unittest.TestCase):
    def stock(self, root):
        for relative, content in {
            'system/system/etc/ueventd.rc': '# system rules\n',
            'vendor/ueventd.rc': '# stock vendor rules\n',
            'vendor/etc/selinux/vendor_property_contexts': 'vendor.existing u:object_r:vendor_default_prop:s0',
            'vendor/etc/selinux/vendor_sepolicy.cil': '(type vendor_rild_prop)\n',
        }.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    def test_tampered_reference_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'manifests').mkdir()
            source = root / 'integration/onerom/upstream'
            source.mkdir(parents=True)
            (source / 'test').write_text('tampered')
            (root / 'manifests/onerom.json').write_text(json.dumps({'files': [{'path': 'test', 'sha': '0' * 40, 'size': 8}]}))
            with patch('integration.onerom.install.ROOT', root):
                with self.assertRaises(ValueError):
                    verify()

    def test_pinned_references_and_disabled_candidates(self):
        manifest = verify()
        self.assertEqual(manifest['commit'], '644f0aacc49ad2410e566de8deb05e6c8211d83d')
        for name in MODULES:
            self.assertTrue((ROOT / 'integration/onerom/upstream/target/beyond1lte/patches' / name / 'disable').is_file())

    def test_init_idempotence_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.stock(root)
            props = root / 'vendor/etc/selinux/vendor_property_contexts'
            props.chmod(0o640)
            legacy_init(root)
            once = props.read_bytes()
            legacy_init(root)
            self.assertEqual(once, props.read_bytes())
            self.assertIn(b'\nvendor.sec.rild.libpath ', once)
            self.assertEqual(props.stat().st_mode & 0o777, 0o640)
            self.assertEqual((root / 'system/system/etc/ueventd.rc').read_text().count('import /vendor/ueventd.rc'), 1)

    def test_unknown_selinux_type_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.stock(root)
            (root / 'vendor/etc/selinux/vendor_sepolicy.cil').write_text('(type other_prop)')
            legacy_init(root)
            props = (root / 'vendor/etc/selinux/vendor_property_contexts').read_text()
            self.assertNotIn('vendor.sec.rild.libpath', props)
            self.assertTrue(props.endswith('\n'))

    def test_existing_ril_mapping_and_import_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.stock(root)
            props = root / 'vendor/etc/selinux/vendor_property_contexts'
            props.write_text('vendor.sec.rild.libpath u:object_r:other_prop:s0\n')
            (root / 'system/system/etc/ueventd.rc').write_text('  import /vendor/ueventd.rc # stock\n')
            legacy_init(root)
            self.assertEqual(props.read_text(), 'vendor.sec.rild.libpath u:object_r:other_prop:s0\n')
            self.assertEqual((root / 'system/system/etc/ueventd.rc').read_text().count('import'), 1)

    def test_missing_required_input_fails_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.stock(root)
            (root / 'vendor/etc/selinux/vendor_sepolicy.cil').unlink()
            path = root / 'system/system/etc/ueventd.rc'
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                legacy_init(root)
            self.assertEqual(path.read_bytes(), before)

    def test_actual_donor_sdk_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / 'SM-S926B_EUX/system/system/build.prop'
            p.parent.mkdir(parents=True)
            p.write_text('ro.build.version.sdk=37\n')
            self.assertEqual(donor_sdk(root, 'SM-S926B/EUX'), 37)
            p.write_text('ro.build.version.sdk=37\nro.build.version.sdk=36\n')
            with self.assertRaises(ValueError):
                donor_sdk(root, 'SM-S926B/EUX')
            with self.assertRaises(ValueError):
                donor_sdk(root, '../EUX')

    def test_bluetooth_real_script_execution_uses_actual_sdk(self):
        text = (ROOT / 'reference/artisan-s10/platform/exynos9820/patches/miscs/customize.sh').read_text()
        patched = bluetooth_policy(text)
        subprocess.run(['bash', '-n'], input=patched, text=True, check=True)
        # Execute the transformed Bluetooth tail with mocked build primitives,
        # but the real SDK reader and real extracted-file layout.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prop = root / 'fw/SM-S926B_EUX/system/system/build.prop'
            prop.parent.mkdir(parents=True)
            library = root / 'work/system/system/lib64/libbluetooth_jni.so'
            library.parent.mkdir(parents=True)
            library.touch()
            snippet = patched[patched.index('_BEYOUD_BT_API='):]
            harness = 'ADD_TO_WORK_DIR() { echo OLD_APEX; }; HEX_PATCH() { echo OLD_HEX; }; LOG_STEP_OUT() { :; };\n' + snippet
            script = root / 'policy.sh'
            script.write_text(harness)
            for actual, declared, expected in [(36, '37', 'OLD_APEX\nOLD_HEX\n'), (37, '36', '')]:
                prop.write_text(f'ro.build.version.sdk={actual}\n')
                env = dict(os.environ, SRC_DIR=str(ROOT), FW_DIR=str(root / 'fw'), WORK_DIR=str(root / 'work'), SOURCE_FIRMWARE='SM-S926B/EUX', SOURCE_API_LEVEL=declared)
                result = subprocess.run(['bash', '-c', 'source "$1"', 'bash', str(script)], env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)
        with self.assertRaises(ValueError):
            bluetooth_policy(text.replace('289767394805003736008052', 'changed'))

    def test_overlay_scopes_and_collision(self):
        for codename in ('beyond1lte', 'beyond2lte'):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = root / 'platform/exynos9820/patches/miscs/customize.sh'
                path.parent.mkdir(parents=True)
                original = (ROOT / 'reference/artisan-s10/platform/exynos9820/patches/miscs/customize.sh').read_text()
                path.write_text(original)
                info = install(root, codename)
                self.assertEqual(bool(info['disabled_candidates']), codename == 'beyond1lte')
                for name in MODULES:
                    self.assertEqual((root / 'target/beyond1lte/patches' / name / 'disable').is_file(), codename == 'beyond1lte')
                self.assertTrue((root / 'platform/exynos9820/patches/zz_beyoud_legacy_init/customize.sh').is_file())
                with self.assertRaises(ValueError):
                    install(root, codename)
