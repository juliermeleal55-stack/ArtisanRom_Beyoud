import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

metadata = load('firmware_metadata', 'integration/samloader/metadata.py')
prepare = load('prepare_lock', 'scripts/prepare_workspace.py')
RECORD = dict(model='SM-S926B', csc='EUX', version='AP/CSC/CP/AP', size=100)


class FirmwareLockTests(unittest.TestCase):
    def test_lookup_is_exact_and_does_not_require_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lock.json'
            path.write_text(json.dumps(dict(schema_version=1, firmwares=[RECORD])))
            self.assertEqual(metadata.get(path, 'SM-S926B', 'EUX')['version'], RECORD['version'])
            with self.assertRaises(ValueError):
                metadata.get(path, 'SM-G975F', 'AUT')

    def test_duplicate_versions_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lock.json'
            path.write_text(json.dumps(dict(schema_version=1, firmwares=[RECORD, RECORD])))
            with self.assertRaises(ValueError):
                metadata.get(path, 'SM-S926B', 'EUX')

    def test_invalid_records_rejected(self):
        for updates in ({'version': ''}, {'size': 0}, {'size': True}, {'model': '../escape'}, {'csc': 'EUX/'}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                metadata.validate(dict(RECORD, **updates))

    def test_failed_second_probe_does_not_leave_stale_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'out').mkdir()
            lock = root / 'out/firmware-lock.json'
            lock.write_text('stale')
            (root / 'out/config.sh').write_text('SOURCE_FIRMWARE="SM-S926B/EUX/ignored"\nTARGET_FIRMWARE="SM-G975F/AUT/ignored"\n')
            results = [subprocess.CompletedProcess([], 0, 'BEYOUD_FIRMWARE\tSM-S926B\tEUX\tAP/CSC/CP/AP\t100\n', ''), subprocess.CompletedProcess([], 1, '', 'failed')]
            with patch.object(metadata.subprocess, 'run', side_effect=results), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(subprocess.CalledProcessError):
                    metadata.resolve(root)
            self.assertFalse(lock.exists())

    def test_complete_probe_lock_covers_source_target_and_extras(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'out').mkdir()
            (root / 'out/config.sh').write_text('SOURCE_FIRMWARE="SM-S926B/EUX/ignored"\nTARGET_FIRMWARE="SM-G975F/AUT/ignored"\nSOURCE_EXTRA_FIRMWARES="SM-G985F/ZTO/ignored"\n')
            def probe(argv, **kwargs):
                return subprocess.CompletedProcess([], 0, f'BEYOUD_FIRMWARE\t{argv[1]}\t{argv[2]}\tAP/CSC/CP/AP\t100\n', '')
            with patch.object(metadata.subprocess, 'run', side_effect=probe), patch.object(metadata.shutil, 'disk_usage') as disk, contextlib.redirect_stdout(io.StringIO()):
                disk.return_value.free = 100 * 1024**3
                metadata.resolve(root)
            lock = root / 'out/firmware-lock.json'
            self.assertEqual(len(json.loads(lock.read_text())['firmwares']), 3)
            self.assertEqual(metadata.get(lock, 'SM-G975F', 'AUT')['version'], 'AP/CSC/CP/AP')

    def test_patched_helper_has_no_fota_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'scripts/utils/firmware_utils.sh'
            path.parent.mkdir(parents=True)
            path.write_text('GET_LATEST_FIRMWARE()\n{\n    curl https://old-query.invalid\n}\n')
            prepare.patch_firmware_lookup(root)
            self.assertNotIn('curl', path.read_text())
            self.assertIn('firmware-lock.json', path.read_text())
            subprocess.run(['bash', '-n', str(path)], check=True)

    def test_all_workers_waited_and_earlier_failure_is_not_hidden(self):
        # First worker fails, second succeeds: old wait PID1 PID2 incorrectly returned 0.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts/internal').mkdir(parents=True)
            make = root / 'scripts/make_rom.sh'
            make.write_text('''#!/bin/bash
        while IFS= read -r f; do
            (exit "$f") &
        done < <(find "$APKTOOL_DIR" -type f)
        wait $(jobs -p) || exit 1
''')
            zip_script = root / 'scripts/internal/build_flashable_zip.sh'
            loop = '''
while IFS= read -r f; do
    (exit 0
    ) &
done < <(echo x)
wait $(jobs -p) || exit 1
'''
            zip_script.write_text(loop * 2)
            prepare.patch_parallel_builds(root)
            text = make.read_text().replace('find "$APKTOOL_DIR" -type f', "printf '7\\n0\\n'")
            result = subprocess.run(['bash', '-c', text], capture_output=True)
            self.assertEqual(result.returncode, 1)
            subprocess.run(['bash', '-n', str(zip_script)], check=True)
