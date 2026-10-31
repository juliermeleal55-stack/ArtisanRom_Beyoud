#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve firmware once via SmartDownload; share an atomic lock with download AND extraction."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def validate(record):
    if not re.fullmatch(r'SM-[A-Z0-9]+', record['model']) or not re.fullmatch(r'[A-Z0-9]{3}', record['csc']):
        raise ValueError('Invalid model/CSC in firmware metadata')
    if not re.fullmatch(r'[A-Z0-9]+(?:/[A-Z0-9]+){3}', record['version']):
        raise ValueError('Expected a four-part resolved firmware version')
    if type(record['size']) is not int or record['size'] <= 0:
        raise ValueError('Invalid firmware package size')
    return record


def get(lock, model, csc):
    data = json.loads(lock.read_text())
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported firmware lock schema')
    records = [validate(item) for item in data['firmwares']]
    matches = [item for item in records if item['model'] == model and item['csc'] == csc]
    if len(matches) != 1:
        raise ValueError(f'Missing or duplicate resolved firmware for {model}/{csc}; run probe_firmware.sh first')
    return matches[0]


def configured_pairs(config):
    values = dict(re.findall(r'^([A-Z_]+)="([^"\n]*)"$', config.read_text(), re.M))
    descriptors = [values['SOURCE_FIRMWARE'], values['TARGET_FIRMWARE']]
    for key in ('SOURCE_EXTRA_FIRMWARES', 'TARGET_EXTRA_FIRMWARES'):
        descriptors.extend(filter(None, values.get(key, '').split(':')))
    pairs = []
    for descriptor in descriptors:
        model, csc, *_ = descriptor.split('/')
        if (model, csc) not in pairs:
            pairs.append((model, csc))
    return pairs


def resolve(workspace):
    lock = workspace / 'out/firmware-lock.json'
    # Never allow a previous partial/stale probe to be reused after failure.
    lock.unlink(missing_ok=True)
    records = []
    binary = workspace / 'out/tools/bin/beyoud-firmware-probe'
    for model, csc in configured_pairs(workspace / 'out/config.sh'):
        result = subprocess.run([str(binary), model, csc], text=True, capture_output=True, timeout=180)
        print(result.stdout, end='', flush=True)
        print(result.stderr, end='', file=sys.stderr, flush=True)
        result.check_returncode()
        lines = [line.split('\t') for line in result.stdout.splitlines() if line.startswith('BEYOUD_FIRMWARE\t')]
        if len(lines) != 1 or len(lines[0]) != 5:
            raise ValueError('Probe did not produce exactly one valid machine-readable record')
        _, resolved_model, resolved_csc, version, size = lines[0]
        record = validate(dict(model=resolved_model, csc=resolved_csc, version=version, size=int(size)))
        if (resolved_model, resolved_csc) != (model, csc):
            raise ValueError('Probe identity differs from configured firmware')
        records.append(record)
    temp = lock.with_suffix('.tmp')
    temp.write_text(json.dumps({'schema_version': 1, 'firmwares': records}, indent=2) + '\n')
    os.replace(temp, lock)
    # Download + tar expansion of the largest package coexist in the legacy pipeline.
    required = max(item['size'] for item in records) * 2 + 8 * 1024**3
    free = shutil.disk_usage(workspace).free
    print(f'Disk preflight: free={free} minimum={required} bytes (full build may need more)', flush=True)
    if free < required:
        raise ValueError('Insufficient disk for largest firmware download + Odin expansion; use a larger/clean runner')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    read = sub.add_parser('get')
    read.add_argument('lock', type=Path)
    read.add_argument('model')
    read.add_argument('csc')
    probe = sub.add_parser('resolve')
    probe.add_argument('workspace', type=Path)
    args = parser.parse_args()
    if args.command == 'get':
        print(get(args.lock, args.model, args.csc)['version'])
    else:
        resolve(args.workspace)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f'Firmware metadata error: {exc}', file=sys.stderr)
        sys.exit(1)
