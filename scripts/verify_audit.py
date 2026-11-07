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
    rebases = json.loads((ROOT / 'manifests/donor-patch-rebases.json').read_text())
    if rebases['commit'] != json.loads((ROOT / 'manifests/onerom.json').read_text())['commit']:
        raise ValueError('Rebases differ from audited OneROM revision')
    for entry in rebases['files']:
        for key in ('reference', 'installed'):
            path = ROOT / entry[key]
            if not path.resolve().is_relative_to(ROOT):
                raise ValueError('Unsafe service rebase evidence path')
            blob(path, entry if key == 'reference' else entry['installed_evidence'])
            count += 1
    layout = json.loads((ROOT / 'manifests/onerom-layout-review.json').read_text())
    if layout['commit'] != rebases['commit']:
        raise ValueError('OneROM layout review differs from audited revision')
    for entry in layout['files']:
        path = ROOT / entry['reference']
        if not path.resolve().is_relative_to((ROOT / 'reference/onerom-layout-review').resolve()):
            raise ValueError('Unsafe OneROM layout evidence path')
        blob(path, entry)
        count += 1
    repart = json.loads((ROOT / 'manifests/extreme-repartition.json').read_text())
    if not re.fullmatch('[0-9a-f]{40}',repart['commit']):raise ValueError('Unpinned repartition evidence')
    for entry in repart['files']:
        path = ROOT / entry['reference']
        if not path.resolve().is_relative_to((ROOT / 'reference/extreme-repartition').resolve()):raise ValueError('Unsafe repartition evidence')
        blob(path,entry);count+=1
    profile=json.loads((ROOT/'integration/partition_layouts/extreme-default.json').read_text())
    if profile['commit']!=repart['commit']:raise ValueError('Repartition profile provenance mismatch')
    script=(ROOT/'reference/extreme-repartition/repartitioner/extreme/repartition.sh').read_text()
    for partition,size in profile['image_size_caps'].items():
        matches=re.findall(r'^'+partition+r'size=([0-9]+)$',script,re.M)
        if len(matches)!=1 or int(matches[0])*1048576!=size:raise ValueError('Profile differs from upstream default partition sizes')
    return count


if __name__ == '__main__':
    print(f'{verify()} cross-audit/build evidence files verified')
