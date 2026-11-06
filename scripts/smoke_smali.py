#!/usr/bin/env python3
"""Exercise the actual built assembler before spending time downloading firmware."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

API_DEX={23:35,25:37,27:38,29:39,34:40,35:41}


def verify(data, version):
    if len(data)<112 or data[:8]!=f'dex\n{version:03d}\0'.encode():
        raise ValueError('Assembler produced an unexpected DEX format')
    if struct.unpack_from('<I',data,32)[0]!=len(data):
        raise ValueError('DEX file size mismatch')
    if data[12:32]!=hashlib.sha1(data[32:]).digest():
        raise ValueError('DEX SHA1 mismatch')
    if struct.unpack_from('<I',data,8)[0]!=(zlib.adler32(data[12:]) & 0xffffffff):
        raise ValueError('DEX checksum mismatch')


def smoke(workspace):
    jar=workspace/'out/tools/bin/android-smali.jar'
    if not jar.is_file():raise ValueError('Built Smali fat JAR missing')
    overlay=(workspace/'scripts/apktool.sh').read_text()
    mapper=overlay[overlay.index('DEX_TO_API()\n'):overlay.index('PREPARE_SCRIPT()\n')]
    original=(workspace/'scripts/utils/build_utils.sh').read_text()
    begin=original.index('READ_BYTES_AT()\n')
    reader=original[begin:original.index('\n# [',begin)]
    harness='LOGE() { echo "$*" >&2; }; _CHECK_NON_EMPTY_PARAM() { [[ -n "$2" ]]; };\n'+reader+'\n'+mapper+'\nDEX_TO_API "$1"\n'
    with tempfile.TemporaryDirectory(prefix='beyoud-smali-') as directory:
        root=Path(directory);source=root/'source';source.mkdir()
        (source/'Probe.smali').write_text('.class public Lbeyoud/Probe;\n.super Ljava/lang/Object;\n.method public static probe()I\n.locals 1\nconst/4 v0, 0x1\nreturn v0\n.end method\n')
        for api,version in API_DEX.items():
            output=root/f'api-{api}.dex'
            subprocess.run(['java','-jar',str(jar),'a','-a',str(api),'-j','1','-o',str(output),str(source)],check=True)
            verify(output.read_bytes(),version)
            mapped=subprocess.run(['bash','-c',harness,'smali-mapping-test',str(output)],check=True,capture_output=True,text=True)
            if mapped.stdout.strip()!=str(api):
                raise ValueError(f'Actual APKTool DEX mapping differs: API {api}, result {mapped.stdout!r}')
            print(f'Smali real assembly and actual APKTool mapping verified: API {api} -> DEX {version:03d}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('workspace',type=Path);args=parser.parse_args()
    try:smoke(args.workspace)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:parser.exit(1,f'Smali smoke test failed: {exc}\n')
