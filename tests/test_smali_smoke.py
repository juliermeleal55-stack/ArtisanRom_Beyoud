import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib
from scripts.smoke_smali import API_DEX, verify, smoke


def dex(version):
    data=bytearray(112);data[:8]=f'dex\n{version:03d}\0'.encode()
    struct.pack_into('<I',data,32,len(data));data[12:32]=hashlib.sha1(data[32:]).digest()
    struct.pack_into('<I',data,8,zlib.adler32(data[12:]) & 0xffffffff)
    return data


class SmaliSmokeTests(unittest.TestCase):
    def test_valid_and_corrupt_dex_headers(self):
        for version in API_DEX.values():verify(dex(version),version)
        for offset in (0,8,12,32,100):
            data=dex(41);data[offset]^=1
            with self.assertRaises(ValueError):verify(data,41)

    def test_real_command_contract_and_all_supported_format_mappings(self):
        calls=[]
        def assemble(command,check):
            self.assertTrue(check);self.assertEqual(command[:2],['java','-jar'])
            api=int(command[command.index('-a')+1]);calls.append(api)
            Path(command[command.index('-o')+1]).write_bytes(dex(API_DEX[api]))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);jar=root/'out/tools/bin/android-smali.jar'
            jar.parent.mkdir(parents=True);jar.touch()
            with patch('scripts.smoke_smali.subprocess.run',side_effect=assemble):smoke(root)
        self.assertEqual(calls,list(API_DEX))
        self.assertNotIn(36,calls)
