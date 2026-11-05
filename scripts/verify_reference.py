#!/usr/bin/env python3
"""Verify imported legacy text against Git blob IDs; never execute it."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify():
    manifest = json.loads((ROOT / 'manifests/artisan-s10-files.json').read_text())
    count = 0
    for entry in manifest['files']:
        if not entry['vendored_text']:
            continue
        path = ROOT / 'reference/artisan-s10' / entry['path']
        data = path.read_bytes()
        digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if digest != entry['sha'] or len(data) != entry['size']:
            raise ValueError(f'Reference modified: {entry["path"]}')
        count += 1
    return count


if __name__ == '__main__':
    print(f'{verify()} Artisan reference files verified')
    sys.path.insert(0, str(ROOT))
    from integration.onerom.install import verify as verify_onerom
    print(f'{len(verify_onerom()["files"])} OneROM reference files verified')
