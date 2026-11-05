import importlib.util
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare', ROOT / 'scripts/prepare_workspace.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class WorkspaceTests(unittest.TestCase):
    def test_adapter_preserves_separate_target(self):
        result = subprocess.run(['bash', '-c',
            'SRC_DIR="$1"; source "$1/integration/artisan/essi_64.sh"; '
            'printf "%s|%s|%s" "$SOURCE_API_LEVEL" "$SOURCE_FIRMWARE" "${TARGET_PLATFORM-unset}"',
            'test', str(ROOT)], check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout, '37|SM-S926B/EUX/350330051234562|unset')

    def test_overlay_only_changes_assertions_and_empty_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            target = workspace / 'target/beyond2lte/config.sh'
            target.parent.mkdir(parents=True)
            original = 'TARGET_CODENAME="beyond2lte"\nTARGET_ASSERT_MODEL=("SM-G975F" "SM-G975N")\nTARGET_EXTRA_FIRMWARES=("")\nTARGET_OS_FILE_SYSTEM="ext4"\nTARGET_SUPER_PARTITION_SIZE=0\n'
            target.write_text(original)
            (workspace / 'unica/configs').mkdir(parents=True)
            (workspace / 'unica/configs/version.sh').write_text('ROM_VERSION="3.1.1"\n')
            from test_smart_download import LEGACY
            (workspace / 'scripts').mkdir()
            (workspace / 'scripts/download_fw.sh').write_text(LEGACY)
            misc = workspace / 'platform/exynos9820/patches/miscs/customize.sh'
            misc.parent.mkdir(parents=True, exist_ok=True)
            misc.write_text((ROOT / 'reference/artisan-s10/platform/exynos9820/patches/miscs/customize.sh').read_text())
            with patch.object(prepare, 'install_preflight'), patch.object(prepare, 'install_framework'), patch.object(prepare, 'apply_build_policy'), patch.object(prepare, 'patch_firmware_lookup'), patch.object(prepare, 'patch_parallel_builds'), patch.object(prepare, 'patch_sequential_firmwares'):
                prepare.apply_overlay(workspace)
            self.assertIn('0.1.0-alpha1', (workspace / 'unica/configs/version.sh').read_text())
            self.assertIn('TARGET_ASSERT_MODEL=("SM-G975F")', target.read_text())
            self.assertIn('TARGET_SUPER_PARTITION_SIZE=0', target.read_text())
            self.assertIn('TARGET_OS_FILE_SYSTEM="ext4"', target.read_text())

    def test_bad_digest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.tar.gz'
            path.write_bytes(b'not an archive')
            with self.assertRaises(ValueError):
                prepare.check_archive(path)

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'bad.tar.gz'
            with tarfile.open(path, 'w:gz') as archive:
                member = tarfile.TarInfo(f'ArtisanROM_old-{prepare.BASE_COMMIT}/../escape')
                member.size = 1
                archive.addfile(member, io.BytesIO(b'x'))
            dest = root / 'dest'
            dest.mkdir()
            with self.assertRaises(ValueError):
                prepare.extract(path, dest)
            self.assertFalse((root / 'escape').exists())

    def test_symlink_cannot_redirect_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'bad.tar.gz'
            with tarfile.open(path, 'w:gz') as archive:
                prefix = f'ArtisanROM_old-{prepare.BASE_COMMIT}/'
                member = tarfile.TarInfo(prefix + 'link')
                member.type = tarfile.SYMTYPE
                member.linkname = str(root)
                archive.addfile(member)
                file = tarfile.TarInfo(prefix + 'link/escape')
                file.size = 1
                archive.addfile(file, io.BytesIO(b'x'))
            dest = root / 'dest'
            dest.mkdir()
            with self.assertRaises(ValueError):
                prepare.extract(path, dest)
            self.assertFalse((root / 'escape').exists())
