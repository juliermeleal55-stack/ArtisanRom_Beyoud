#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate the effective donor/platform/device debloat plan before deletions."""
import json
from pathlib import Path, PurePosixPath
import sys

PARTITIONS = ('odm', 'product', 'system', 'system_ext', 'vendor', 'prism', 'optics')
PROTECTED = {
    'system': ('system/bin/init', 'system/bin/app_process', 'system/bin/app_process32',
               'system/bin/app_process64', 'system/bin/servicemanager', 'system/bin/hwservicemanager',
               'system/bin/surfaceflinger', 'system/bin/vold', 'system/bin/netd', 'system/bin/keystore2',
               'system/etc/init/hw', 'system/framework/framework.jar', 'system/framework/services.jar',
               'system/priv-app/SystemUI', 'system/priv-app/SecSettings',
               'system/priv-app/TelephonyProvider', 'system/priv-app/TeleService'),
    'product': ('priv-app/SystemUI', 'priv-app/TelephonyProvider', 'priv-app/TeleService'),
    'system_ext': ('priv-app/SystemUI',),
    'vendor': ('etc/selinux', 'build.prop', 'bin/hw'),
}


def plan(values):
    if len(values) != len(PARTITIONS):
        raise ValueError('Expected all partition debloat lists')
    result = {}
    for partition, value in zip(PARTITIONS, values):
        entries = sorted(set(line.strip() for line in value.splitlines() if line.strip()))
        for entry in entries:
            path = PurePosixPath(entry)
            if (entry.startswith('/') or any(part in ('.', '..') for part in entry.split('/'))
                    or any(char in entry for char in '*?[]$`\\\0') or str(path) != entry):
                raise ValueError(f'Unsafe debloat path: {partition}/{entry}')
            for protected in PROTECTED.get(partition, ()):
                if entry == protected or protected.startswith(entry + '/') or entry.startswith(protected + '/'):
                    raise ValueError(f'Boot-critical debloat deletion requires review: {partition}/{entry}')
        result[partition] = entries
    return result


if __name__ == '__main__':
    destination = Path(sys.argv[1])
    try:
        result = plan(sys.argv[2:])
    except ValueError as exc:
        print(f'Debloat blocked: {exc}', file=sys.stderr)
        sys.exit(1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({'schema_version': 1, 'partitions': result}, indent=2) + '\n')
    print(f'Debloat plan checked: {sum(map(len, result.values()))} unique paths; {destination}')
