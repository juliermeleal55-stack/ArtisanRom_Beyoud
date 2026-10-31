#!/usr/bin/env python3
"""Structural alpha artifact checks; never a certification of boot or safety."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


def check_package(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('Corrupted ZIP')
        names = set(archive.namelist())
        required = {'META-INF/com/google/android/update-binary',
                    'META-INF/com/google/android/updater-script', 'boot.img', 'dtbo.img'}
        if not required <= names:
            raise ValueError(f'Missing installer components: {required - names}')
        script = archive.read('META-INF/com/google/android/updater-script').decode()
        if 'SM-G975F' not in script or any(model in script for model in ('SM-G975N', 'SM-G985F', 'SM-G986B')):
            raise ValueError('Unexpected device assertions')
        if not any(name.startswith('system.') and '.dat' in name for name in names):
            raise ValueError('Missing system payload')
        for image in ('boot.img', 'dtbo.img'):
            if archive.getinfo(image).file_size == 0:
                raise ValueError(f'Empty {image}')


def collect(workspace, destination):
    marker = json.loads((workspace / 'BEYOUD-WORKSPACE.json').read_text())
    if marker['target'] != 'SM-G975F':
        raise ValueError('Not a G975F workspace')
    candidates = list((workspace / 'out').glob('*alpha1*beyond2lte*.zip'))
    if len(candidates) != 1:
        raise ValueError(f'Expected exactly one alpha ZIP, found {len(candidates)}')
    source = candidates[0]
    check_package(source)
    destination.mkdir(parents=True, exist_ok=False)
    filename = 'Beyoud-SM-G975F-0.1.0-alpha1-UNTESTED.zip'
    output = destination / filename
    shutil.copyfile(source, output)
    digest = hashlib.sha256()
    with output.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    (destination / 'SHA256SUMS').write_text(f'{digest.hexdigest()}  {filename}\n')
    (destination / 'WARNING.txt').write_text(
        'EXPERIMENTAL UNTESTED ALPHA — SM-G975F ONLY\n'
        'Build success and structural checks DO NOT prove boot or flash safety.\n'
        'May erase data, fail to boot or break calls, camera, encryption and other features.\n'
        'Not for a primary phone. No hardware validation has been performed.\n'
        'Have an independently verified stock recovery procedure and backups before any test.\n')
    (destination / 'provenance.json').write_text(json.dumps(marker, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    collect(args.workspace, args.destination)
