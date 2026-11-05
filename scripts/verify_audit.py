#!/usr/bin/env python3
"""Offline verification of pinned cross-audit evidence and build fixtures."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def blob(path, entry):
    data = path.read_bytes()
    if len(data) != entry['size'] or hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != entry['sha']:
        raise ValueError(f'Audit evidence modified: {path}')


def verify():
    audit = json.loads((ROOT / 'manifests/cross-audit.json').read_text())
    count = 0
    for name, source in audit['sources'].items():
        if not re.fullmatch('[0-9a-f]{40}', source['commit']) or source['inventory_truncated']:
            raise ValueError('Unpinned or incomplete source inventory')
        for entry in source['evidence']:
            path = ROOT / 'reference/cross-audit' / name / entry['path']
            if not path.resolve().is_relative_to((ROOT / 'reference/cross-audit').resolve()):
                raise ValueError('Unsafe audit evidence path')
            blob(path, entry)
            count += 1
    fixtures = json.loads((ROOT / 'manifests/build-scripts.json').read_text())
    if fixtures['commit'] != audit['sources']['artisan_s10']['commit']:
        raise ValueError('Build fixtures differ from audited base')
    for entry in fixtures['files']:
        blob(ROOT / 'reference/build' / entry['path'], entry)
        count += 1
    return count


if __name__ == '__main__':
    print(f'{verify()} cross-audit/build evidence files verified')
