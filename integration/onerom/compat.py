#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Guarded adaptations inspired by OneROM; no binary/HAL substitutions."""
import argparse
from pathlib import Path
import re


def checked(root, relative):
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f'Missing or unsafe compatibility input: {relative}')
    return path


def donor_sdk(firmwares, descriptor):
    parts = descriptor.split('/')
    if len(parts) not in (2, 3) or not re.fullmatch(r'SM-[A-Z0-9]+', parts[0]) or not re.fullmatch(r'[A-Z0-9]+', parts[1]):
        raise ValueError('Invalid source firmware descriptor')
    path = checked(firmwares, f'{parts[0]}_{parts[1]}/system/system/build.prop')
    values = [line.partition('=')[2].strip() for line in path.read_text().splitlines()
              if line.partition('=')[0].strip() == 'ro.build.version.sdk']
    if len(values) != 1 or not re.fullmatch(r'[0-9]+', values[0]) or not 1 <= int(values[0]) <= 1000:
        raise ValueError('Expected exactly one valid actual donor SDK')
    return int(values[0])


def legacy_init(work):
    # Prevalidate every required input before touching any file.
    uevent = checked(work, 'system/system/etc/ueventd.rc')
    checked(work, 'vendor/ueventd.rc')
    contexts = checked(work, 'vendor/etc/selinux/vendor_property_contexts')
    policy = checked(work, 'vendor/etc/selinux/vendor_sepolicy.cil').read_text()
    text, props = uevent.read_text(), contexts.read_text()
    if '\0' in text or '\0' in props:
        raise ValueError('Unexpected binary init/context input')
    if not re.search(r'^\s*import\s+/vendor/ueventd\.rc\s*(?:#.*)?$', text, re.M):
        text = text.rstrip('\n') + '\nimport /vendor/ueventd.rc\n'
    # Do not introduce an SELinux type that the stock vendor does not define.
    if (not re.search(r'^\s*vendor\.sec\.rild\.libpath\s+', props, re.M)
            and re.search(r'\(type\s+vendor_rild_prop\)', policy)):
        props = props.rstrip('\n') + '\nvendor.sec.rild.libpath u:object_r:vendor_rild_prop:s0\n'
    elif props and not props.endswith('\n'):
        props += '\n'
    # In-place writes preserve the existing mode/inode and build metadata maps.
    if text != uevent.read_text():
        uevent.write_text(text)
    if props != contexts.read_text():
        contexts.write_text(props)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sdk = sub.add_parser('sdk')
    sdk.add_argument('firmwares', type=Path)
    sdk.add_argument('descriptor')
    init = sub.add_parser('init')
    init.add_argument('work', type=Path)
    args = parser.parse_args()
    if args.command == 'sdk':
        print(donor_sdk(args.firmwares, args.descriptor))
    else:
        legacy_init(args.work)
