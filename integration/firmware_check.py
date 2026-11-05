#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check actual SDK/layout before applying a declared donor patch schema."""
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integration.package_inputs import atomic_json, read_prop
from integration.samloader.metadata import configured_firmwares, get
from integration.targets import from_marker


def inspect(workspace):
    codename, device = from_marker(json.loads((workspace / 'BEYOUD-WORKSPACE.json').read_text()))
    out = workspace / 'out'
    config = dict(re.findall(r'^([A-Z_]+)="([^"\n]*)"$', (out / 'config.sh').read_text(), re.M))
    results = []
    for role, descriptor in zip(('source', 'target'), configured_firmwares(out / 'config.sh')):
        model, csc, *_ = descriptor.split('/')
        record = get(out / 'firmware-lock.json', model, csc)
        root = out / 'fw' / f'{model}_{csc}'
        if root.is_symlink() or not root.resolve().is_relative_to(workspace.resolve()):
            raise ValueError('Unsafe extracted firmware root')
        if (root / '.extracted').read_text().strip() != record['version']:
            raise ValueError('Firmware extraction differs from lock')
        sdk = read_prop(root / 'system/system/build.prop', 'ro.build.version.sdk')
        expected = config[f'{role.upper()}_API_LEVEL']
        if sdk != expected:
            raise ValueError(f'{role} actual SDK={sdk}, declared SDK={expected}; select/adapt the donor schema, do not bypass this check')
        if role == 'target' and model != device['model']:
            raise ValueError('Wrong stock target firmware')
        separate = (root / 'system_ext').is_dir()
        embedded = (root / 'system/system/system_ext').is_dir()
        if role == 'source' and config.get('SOURCE_HAS_SYSTEM_EXT') == 'true' and not (separate or embedded):
            raise ValueError('Declared donor system_ext is absent; adapter layout needs review')
        results.append(dict(role=role, model=model, csc=csc, version=record['version'], sdk=int(sdk),
                            separate_system_ext=separate, embedded_system_ext=embedded))
    if len(results) != 2:
        raise ValueError('Expected two firmware roles')
    result = dict(schema_version=1, codename=codename, status='properties-checked-not-boot-validated', firmwares=results)
    atomic_json(out / 'beyoud-firmware-inspection.json', result)
    return result


if __name__ == '__main__':
    print(json.dumps(inspect(Path(sys.argv[1]).resolve()), indent=2))
