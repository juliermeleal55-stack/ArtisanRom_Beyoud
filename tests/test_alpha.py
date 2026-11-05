import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('alpha', ROOT / 'scripts/collect_alpha.py')
alpha = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alpha)


def package(path, model='SM-G975F', boot=b'candidate-boot', payload=True):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('META-INF/com/google/android/update-binary', b'installer')
        archive.writestr('META-INF/com/google/android/updater-script', f'getprop("ro.product.model") == "{model}"')
        archive.writestr('boot.img', boot)
        archive.writestr('dtbo.img', b'candidate-dtbo')
        if payload:
            archive.writestr('system.new.dat.br', b'candidate-system')


class AlphaTests(unittest.TestCase):
    def test_wrong_model_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rom.zip'
            package(path, model='SM-G985F')
            with self.assertRaises(ValueError):
                alpha.check_package(path)

    def test_empty_boot_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rom.zip'
            package(path, boot=b'')
            with self.assertRaises(ValueError):
                alpha.check_package(path)

    def test_missing_system_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rom.zip'
            package(path, payload=False)
            with self.assertRaises(ValueError):
                alpha.check_package(path)

    def test_no_zip_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / 'work'
            workspace.mkdir()
            (workspace / 'BEYOUD-WORKSPACE.json').write_text(json.dumps({'target': 'SM-G975F'}))
            dest = Path(tmp) / 'output'
            with self.assertRaises(ValueError):
                alpha.collect(workspace, dest)
            self.assertFalse(dest.exists())

    def test_structural_checks_are_not_hardware_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / 'work'
            (workspace / 'out').mkdir(parents=True)
            (workspace / 'BEYOUD-WORKSPACE.json').write_text(json.dumps({'target': 'SM-G975F', 'flashable_release': False}))
            package(workspace / 'out/ArtisanROM_0.1.0-alpha1_beyond2lte.zip')
            dest = Path(tmp) / 'output'
            alpha.collect(workspace, dest)
            self.assertTrue((dest / 'SHA256SUMS').exists())
            self.assertIn('DO NOT prove boot', (dest / 'WARNING.txt').read_text())

    def test_wrapper_propagates_build_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / 'BEYOUD-WORKSPACE.json').write_text('{"target":"SM-G975F"}')
            (workspace / 'buildenv.sh').write_text('return 0\n')
            (workspace / 'integration').mkdir()
            (workspace / 'integration/build.py').write_text('import sys; print("failed-build"); sys.exit(7)\n')
            scripts = workspace / 'scripts'
            scripts.mkdir()
            make = scripts / 'make_rom.sh'
            make.write_text('#!/bin/bash\necho failed-build\nexit 7\n')
            make.chmod(0o755)
            result = subprocess.run(['bash', str(ROOT / 'scripts/build_candidate.sh'), str(workspace), 'alpha'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 7)
            self.assertTrue(list((workspace / 'out/beyoud-logs').glob('alpha-*.log')))


if __name__ == '__main__':
    unittest.main()
