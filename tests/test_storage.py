import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('volume', ROOT / 'scripts/select_workspace_volume.py')
volume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(volume)


class StorageTests(unittest.TestCase):
    def test_cleanup_refuses_local_execution(self):
        result = subprocess.run(['bash', str(ROOT / 'scripts/prepare_hosted_storage.sh')],
                                env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('refused', result.stderr)

    def test_volume_with_more_capacity_is_selected(self):
        with patch.object(volume.Path, 'is_dir', return_value=True), patch.object(volume.shutil, 'disk_usage', side_effect=[Mock(free=10), Mock(free=30)]):
            self.assertEqual(volume.choose(Path('/tmp/work'), Path('/mnt/work')), Path('/mnt/work'))

    def test_same_capacity_keeps_default(self):
        with patch.object(volume.Path, 'is_dir', return_value=True), patch.object(volume.shutil, 'disk_usage', return_value=Mock(free=10)):
            self.assertEqual(volume.choose(Path('/tmp/work'), Path('/mnt/work')), Path('/tmp/work'))

    def test_user_archive_cannot_be_discarded(self):
        result = subprocess.run(['python3', str(ROOT / 'scripts/prepare_workspace.py'), '/unused', '--archive', '/user/file.tar.gz', '--discard-archive'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('user-supplied', result.stderr)
