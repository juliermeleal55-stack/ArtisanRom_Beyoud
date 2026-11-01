import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'integration/samloader'
sys.path.insert(0, str(FOLDER))
import stage
import unpack_reclaim as unpack


class ReclaimZipTests(unittest.TestCase):
    def test_roundtrip_stored_and_deflate_with_multiple_members(self):
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / 'firmware.zip'
                contents = random.Random(7).randbytes(18 * 1024**2)
                with zipfile.ZipFile(source, 'w', compression=method) as archive:
                    archive.writestr('AP_test.tar.md5', contents)
                    archive.writestr('nested/BL_test.tar.md5', b'boot test' * 3000)
                released = []
                real_punch = unpack.punch
                def measured(fd, start, end):
                    before = os.fstat(fd).st_blocks
                    result = real_punch(fd, start, end)
                    released.append(before - os.fstat(fd).st_blocks)
                    return result
                with patch.object(unpack, 'punch', side_effect=measured):
                    unpack.unpack(source, root, reserve=0)
                self.assertGreater(sum(released), 0)
                self.assertFalse(source.exists())
                self.assertEqual((root / 'AP_test.tar.md5').read_bytes(), contents)
                self.assertEqual((root / 'nested/BL_test.tar.md5').read_bytes(), b'boot test' * 3000)

    def test_corrupt_crc_does_not_commit_output_or_delete_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'bad.zip'
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('AP.md5', b'original data' * 1000)
            data = bytearray(source.read_bytes())
            offset = data.index(b'original data')
            data[offset] ^= 1
            source.write_bytes(data)
            with self.assertRaises(zipfile.BadZipFile):
                unpack.unpack(source, root, reserve=0)
            self.assertTrue(source.exists())
            self.assertFalse((root / 'AP.md5').exists())
            self.assertFalse(list(root.glob('*.beyoud-partial')))

    def test_unsafe_paths_rejected_before_extracting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'bad.zip'
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('../escape', b'bad')
            with self.assertRaises(ValueError):
                unpack.unpack(source, root, reserve=0)
            self.assertTrue(source.exists())

    def test_unsupported_reclaim_fails_without_full_copy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'firmware.zip'
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('AP.md5', b'data')
            with patch.object(unpack, 'punch', side_effect=OSError('unsupported')):
                with self.assertRaises(OSError):
                    unpack.unpack(source, root, reserve=0)
            self.assertFalse((root / 'AP.md5').exists())
            self.assertTrue(source.exists())


class SequentialStageTests(unittest.TestCase):
    def setup_workspace(self, root):
        (root / 'BEYOUD-WORKSPACE.json').write_text('{}')
        (root / 'out').mkdir()
        (root / 'out/config.sh').write_text('SOURCE_FIRMWARE="SM-S926B/EUX/ignored"\nTARGET_FIRMWARE="SM-G975F/AUT/ignored"\n')
        entries = [dict(model=m, csc=c, version='AP/CSC/CP/AP', size=100) for m, c in [('SM-S926B','EUX'), ('SM-G975F','AUT')]]
        (root / 'out/firmware-lock.json').write_text(json.dumps(dict(schema_version=1, firmwares=entries)))

    def test_download_extract_cleanup_before_next_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.setup_workspace(root)
            calls = []
            def run(argv, **kwargs):
                name = Path(argv[0]).name
                model, csc, *_ = argv[-1].split('/')
                if len(calls) == 2:
                    self.assertFalse((root / 'out/odin/SM-S926B_EUX').exists())
                calls.append((name, model))
                self.assertNotIn('GITHUB_ACTIONS', kwargs['env'])
                odin = root / 'out/odin' / f'{model}_{csc}'
                odin.mkdir(parents=True, exist_ok=True)
                (odin / 'AP.md5').write_text('package')
                if name == 'extract_fw.sh':
                    fw = root / 'out/fw' / f'{model}_{csc}'
                    (fw / 'system').mkdir(parents=True)
                    (fw / '.extracted').write_text('AP/CSC/CP/AP')
                return subprocess.CompletedProcess(argv, 0)
            with patch.object(stage.subprocess, 'run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
                stage.prepare(root)
            self.assertEqual(calls, [('download_fw.sh','SM-S926B'), ('extract_fw.sh','SM-S926B'), ('download_fw.sh','SM-G975F'), ('extract_fw.sh','SM-G975F')])
            self.assertTrue((root / 'out/fw/SM-S926B_EUX/system').is_dir())
            self.assertFalse((root / 'out/odin/SM-G975F_AUT').exists())

    def test_failure_keeps_packages_and_never_starts_next_firmware(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.setup_workspace(root)
            odin = root / 'out/odin/SM-S926B_EUX'
            odin.mkdir(parents=True)
            (odin / 'AP.md5').write_text('package')
            with patch.object(stage.subprocess, 'run', side_effect=[subprocess.CompletedProcess([],0), subprocess.CalledProcessError(1,[])]) as run, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(subprocess.CalledProcessError):
                    stage.prepare(root)
            self.assertEqual(run.call_count, 2)
            self.assertTrue((odin / 'AP.md5').exists())
