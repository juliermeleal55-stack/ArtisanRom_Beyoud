import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from integration.native_analysis import analyze, branch, executable_segments, LEGACY


def elf(code, flags=5):
    data=bytearray(256+len(code))
    data[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI',data,16,3,183,1)
    struct.pack_into('<Q',data,32,64)
    struct.pack_into('<HHH',data,52,64,56,1)
    struct.pack_into('<IIQQQQQQ',data,64,1,flags,256,0x1000,0,len(code),len(code),4096)
    data[256:]=code
    return data


class NativeAnalysisTests(unittest.TestCase):
    def report(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'library.so';path.write_bytes(data)
            before=path.read_bytes();report=analyze(path)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(report['sha256'],hashlib.sha256(before).hexdigest())
            self.assertEqual(report['status'],'analysis-only-no-patch-approved')
            return report

    def test_legacy_sites_are_instruction_aligned_and_read_only(self):
        report=self.report(elf(bytes.fromhex(LEGACY['video_svc'])))
        self.assertEqual(len(report['legacy_exact_sites']['video_svc']),1)
        self.assertEqual(report['inspection_candidates'][0]['address'],0x1000)
        self.assertEqual(report['candidate_count'],1)

    def test_relocated_call_is_only_a_candidate_not_approved_patch(self):
        code=struct.pack('<III',0x94000004,0x2a1a03e0,0x17fffffe)
        report=self.report(elf(code))
        self.assertEqual(report['legacy_exact_sites']['video_svc'],[])
        self.assertEqual(report['candidate_count'],1)
        instructions=report['inspection_candidates'][0]['instructions']
        self.assertEqual(instructions[0]['target'],0x1010)
        self.assertFalse(instructions[0]['target_executable'])
        self.assertEqual(instructions[2]['target'],0x1000)
        self.assertTrue(instructions[2]['target_executable'])

    def test_unaligned_pattern_is_not_an_instruction_match(self):
        report=self.report(elf(b'\0'+bytes.fromhex(LEGACY['video_svc'])+b'\0'*3))
        self.assertEqual(report['candidate_count'],0)
        self.assertEqual(report['legacy_exact_sites']['video_svc'],[])

    def test_non_executable_data_is_not_scanned(self):
        data=elf(b'\x1f\x20\x03\xd5')+bytes.fromhex(LEGACY['video_svc'])
        self.assertEqual(self.report(data)['candidate_count'],0)

    def test_branch_sign_extension(self):
        self.assertEqual(branch(0x97ffffff,0x1000),{'kind':'BL','target':0xffc})
        self.assertEqual(branch(0x14000019,0x1000),{'kind':'B','target':0x1064})
        self.assertEqual(branch(0x34ffffe0,0x1000),{'kind':'CBZ','target':0xffc})
        self.assertIsNone(branch(0xd503201f,0x1000))

    def test_invalid_architecture_bounds_and_permissions_fail_closed(self):
        original=elf(bytes.fromhex(LEGACY['video_svc']))
        cases=[b'not ELF',original[:100]]
        wrong=bytearray(original);struct.pack_into('<H',wrong,18,62);cases.append(wrong)
        wrong=bytearray(original);struct.pack_into('<Q',wrong,32,2**63);cases.append(wrong)
        cases.append(elf(b'\0'*12,flags=4))
        for data in cases:
            with self.subTest(data=data[:20]),self.assertRaises(ValueError):
                executable_segments(data)

    def test_candidate_report_is_bounded(self):
        report=self.report(elf(bytes.fromhex(LEGACY['video_svc'])*150))
        self.assertEqual(report['candidate_count'],150)
        self.assertEqual(len(report['inspection_candidates']),128)
        self.assertTrue(report['candidates_truncated'])
        self.assertEqual(report['legacy_exact_counts']['video_svc'],150)
        self.assertEqual(len(report['legacy_exact_sites']['video_svc']),128)
        self.assertTrue(report['legacy_sites_truncated'])

class DonorCaptureTests(unittest.TestCase):
    def fixture(self, root):
        import json
        out=root/'out';out.mkdir()
        (out/'config.sh').write_text('SOURCE_FIRMWARE="SM-S926B/EUX"\n')
        version='A/A/A/A'
        record=dict(model='SM-S926B',csc='EUX',version=version,size=1024)
        (out/'firmware-lock.json').write_text(json.dumps(dict(schema_version=1,firmwares=[record])))
        firmware=out/'fw/SM-S926B_EUX';firmware.mkdir(parents=True)
        (firmware/'.extracted').write_text(version)
        lib=firmware/'system/system/lib64/libstagefright.so';lib.parent.mkdir(parents=True)
        lib.write_bytes(elf(bytes.fromhex(LEGACY['video_svc'])))
        return firmware,record

    def test_capture_validates_lock_and_produces_analysis_with_same_hash(self):
        import contextlib,io,json
        from scripts.capture_donor_repair_inputs import capture
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.fixture(root);destination=root/'private-inputs'
            with contextlib.redirect_stdout(io.StringIO()):report=capture(root,destination)
            analysis=json.loads((destination/'libstagefright-analysis.json').read_text())
            self.assertEqual(report['files'][0]['sha256'],analysis['sha256'])
            self.assertEqual(analysis['legacy_exact_counts']['video_svc'],1)
            self.assertEqual(report['files'][1]['status'],'unavailable')

    def test_duplicate_metadata_and_stale_extraction_are_rejected(self):
        import json
        from scripts.capture_donor_repair_inputs import capture
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);firmware,record=self.fixture(root)
            (firmware/'.extracted').write_text('different-version')
            with self.assertRaisesRegex(ValueError,'extraction'):
                capture(root,root/'private-inputs')
            self.assertFalse((root/'private-inputs').exists())
            (root/'out/firmware-lock.json').write_text(json.dumps(dict(schema_version=1,firmwares=[record,record])))
            with self.assertRaisesRegex(ValueError,'duplicate'):
                capture(root,root/'private-inputs')
            self.assertFalse((root/'private-inputs').exists())
