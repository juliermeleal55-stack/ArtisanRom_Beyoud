#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Translate the legacy download CLI to pinned samloader-rs; never send device identifiers."""
import argparse
import os
from pathlib import Path
import re
import subprocess


def normalize_version(value):
    parts = value.split('/')
    if len(parts) not in (3, 4) or not all(re.fullmatch(r'[A-Za-z0-9]+', p) for p in parts):
        raise ValueError('Expected a nonempty PDA/CSC/CP[/DATA] firmware version')
    if len(parts) == 3:
        parts.append(parts[0])
    return '/'.join(parts)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-m', required=True)
    parser.add_argument('-r', required=True)
    # Accepted for compatibility only. Never logged or forwarded to SmartDownload.
    parser.add_argument('-i')
    parser.add_argument('-s')
    sub = parser.add_subparsers(dest='command', required=True)
    download = sub.add_parser('download')
    download.add_argument('-v', required=True)
    download.add_argument('-O', required=True)
    return parser.parse_args(argv)


def command(args, binary):
    if not re.fullmatch(r'SM-[A-Z0-9]+', args.m) or not re.fullmatch(r'[A-Z0-9]{3}', args.r):
        raise ValueError('Invalid model or CSC')
    return [str(binary), 'download', '--model', args.m, '--region', args.r,
            '--version', normalize_version(args.v), '--threads', '4', '--out-dir', args.O]


def main():
    args = parse_args()
    binary = Path(os.environ['TOOLS_DIR']) / 'bin/samloader-rs'
    argv = command(args, binary)
    print(f'SmartDownload: model={args.m} CSC={args.r} version={normalize_version(args.v)}', flush=True)
    print('No IMEI or serial number is sent.', flush=True)
    subprocess.run(argv, check=True)


if __name__ == '__main__':
    main()
