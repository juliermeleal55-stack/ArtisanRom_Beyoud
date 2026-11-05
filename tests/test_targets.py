import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from integration.targets import from_marker, select

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

prepare = load('target_prepare', 'scripts/prepare_workspace.py')
alpha = load('target_alpha', 'scripts/collect_alpha.py')


class TargetTests(unittest.TestCase):
    def test_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            from_marker(dict(codename='beyond1lte', target='SM-G975F'))

    def test_snapdragon_and_unknown_rejected(self):
        with self.assertRaises(ValueError):
            from_marker(dict(target='SM-G973U'))
        with self.assertRaises(ValueError):
            select('../beyond1lte')

    def test_legacy_s10plus_marker_still_supported(self):
        self.assertEqual(from_marker(dict(target='SM-G975F'))[0], 'beyond2lte')

    def test_s10_overlay_preserves_own_stock_and_hardware(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / 'target/beyond1lte/config.sh'
            config.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / 'reference/artisan-s10/target/beyond1lte/config.sh', config)
            (root / 'unica/configs').mkdir(parents=True)
            misc = root / 'platform/exynos9820/patches/miscs/customize.sh'
            misc.parent.mkdir(parents=True, exist_ok=True)
            misc.write_text((ROOT / 'reference/artisan-s10/platform/exynos9820/patches/miscs/customize.sh').read_text())
            with patch.object(prepare, 'apply_build_policy'), patch.object(prepare, 'patch_downloader'), patch.object(prepare, 'patch_firmware_lookup'), patch.object(prepare, 'patch_parallel_builds'), patch.object(prepare, 'patch_sequential_firmwares'):
                prepare.apply_overlay(root, 'beyond1lte')
            text = config.read_text()
            self.assertIn('TARGET_ASSERT_MODEL=("SM-G973F")', text)
            self.assertIn('TARGET_FIRMWARE="SM-G973F/AUT/', text)
            self.assertIn('TARGET_PLATFORM="exynos9820"', text)
            self.assertNotIn('SM-G975', text)
            marker = json.loads((root / 'BEYOUD-WORKSPACE.json').read_text())
            self.assertEqual(from_marker(marker)[0], 'beyond1lte')

    def test_s10_package_cannot_be_used_as_s10plus(self):
        from test_alpha import package
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rom.zip'
            package(path, model='SM-G973F')
            alpha.check_package(path, 'SM-G973F')
            with self.assertRaises(ValueError):
                alpha.check_package(path, 'SM-G975F')

    def test_s10_collection_name_and_warning(self):
        from test_alpha import package
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'work'
            (root / 'out').mkdir(parents=True)
            (root / 'BEYOUD-WORKSPACE.json').write_text(json.dumps(dict(target='SM-G973F', codename='beyond1lte')))
            package(root / 'out/ArtisanROM_0.1.0-alpha1_beyond1lte.zip', model='SM-G973F')
            dest = Path(tmp) / 'result'
            alpha.collect(root, dest)
            self.assertTrue((dest / 'Beyoud-SM-G973F-0.1.0-alpha1-UNTESTED.zip').exists())
            self.assertIn('SM-G973F ONLY', (dest / 'WARNING.txt').read_text())
