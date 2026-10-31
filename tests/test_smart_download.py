import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

compat = load('smart_compat', 'integration/samloader/compat.py')
prepare = load('smart_prepare', 'scripts/prepare_workspace.py')
LEGACY = '''#!/bin/bash
if [ ! "$LATEST_FIRMWARE" ]; then
        #exit 1
fi
        (
        samloader -m "$MODEL" -r "$CSC" -i "$IMEI" -s "$SERIAL_NO" download$STR -O "$ODIN_DIR/${MODEL}_${CSC}" || exit 1
        )

        ZIP_FILE="unused"
'''


class SmartDownloadTests(unittest.TestCase):
    def test_no_credentials_forwarded(self):
        args = compat.parse_args(['-m', 'SM-S926B', '-r', 'EUX', '-i', 'not-a-real-imei', '-s', 'not-a-real-serial', 'download', '-v', 'AP/CSC/CP', '-O', '/tmp/firmware output'])
        result = compat.command(args, '/tools/samloader-rs')
        self.assertNotIn('not-a-real-imei', result)
        self.assertNotIn('not-a-real-serial', result)
        self.assertIn('AP/CSC/CP/AP', result)
        self.assertEqual(result[-1], '/tmp/firmware output')

    def test_four_parts_preserved(self):
        self.assertEqual(compat.normalize_version('AP/CSC/CP/DATA'), 'AP/CSC/CP/DATA')

    def test_empty_or_invalid_versions_rejected(self):
        for value in ('', 'AP/CSC', 'AP//CP', 'AP/CSC/CP/EXTRA/FIFTH', 'AP/CSC/CP;false'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compat.normalize_version(value)

    def test_patch_retains_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'scripts/download_fw.sh'
            path.parent.mkdir()
            path.write_text(LEGACY)
            prepare.patch_downloader(root)
            text = path.read_text()
            self.assertIn(') || exit 1', text)
            self.assertIn('download -v "$LATEST_FIRMWARE"', text)
            self.assertNotIn('-i "$IMEI"', text)
            self.assertNotIn('#exit 1', text)
            subprocess.run(['bash', '-n', str(path)], check=True)

    def test_unexpected_script_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts').mkdir()
            (root / 'scripts/download_fw.sh').write_text('unexpected')
            with self.assertRaises(ValueError):
                prepare.patch_downloader(root)

    def test_all_log_types_are_annotated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / 'out/beyoud-logs'
            logs.mkdir(parents=True)
            for name in ('alpha-001.log', 'dependencies-001.log', 'firmware-auth.log'):
                (logs / name).write_text('example error')
            result = subprocess.run(['python3', str(ROOT / 'scripts/annotate_build_failure.py'), str(root)], check=True, capture_output=True, text=True)
            self.assertIn('title=alpha-001.log', result.stdout)
            self.assertEqual(result.stdout.count('::notice'), 3)
