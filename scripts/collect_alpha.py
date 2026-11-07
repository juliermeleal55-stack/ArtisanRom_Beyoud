#!/usr/bin/env python3
"""Structural alpha artifact checks; never a certification of boot or safety."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integration.targets import from_marker
from integration.package_inputs import load as load_package_inputs, image_caps


def check_package(path, model="SM-G975F", allowed_partitions=None):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('Corrupted ZIP')
        names = set(archive.namelist())
        required = {'META-INF/com/google/android/update-binary',
                    'META-INF/com/google/android/updater-script', 'boot.img', 'dtbo.img'}
        if not required <= names:
            raise ValueError(f'Missing installer components: {required - names}')
        script = archive.read('META-INF/com/google/android/updater-script').decode()
        models = set(re.findall(r'SM-[A-Z0-9]+', script))
        if models != {model}:
            raise ValueError('Unexpected device assertions')
        if not any(name.startswith('system.') and '.dat' in name for name in names):
            raise ValueError('Missing system payload')
        if allowed_partitions is not None:
            payloads = {match.group(1) for name in names if (match := re.fullmatch(r'([a-z_]+)\.new\.dat(?:\.br)?', name))}
            writes = set(re.findall(r'block_image_update\(\s*"[^"\n]*/([^/"\n]+)"', script))
            if (payloads | writes) - set(allowed_partitions):
                raise ValueError('Installer references unsupported target partitions')
            if {'super.img','init_boot.img','vendor_boot.img'} & names:
                raise ValueError('Unsupported static S10 boot/super payload')
        for image in ('boot.img', 'dtbo.img'):

            if archive.getinfo(image).file_size == 0:
                raise ValueError(f'Empty {image}')


def collect(workspace, destination):
    marker = json.loads((workspace / 'BEYOUD-WORKSPACE.json').read_text())
    codename, device = from_marker(marker)
    model = device['model']
    candidates = list((workspace / 'out').glob(f'*alpha1*{codename}*.zip'))
    if len(candidates) != 1:
        raise ValueError(f'Expected exactly one alpha ZIP, found {len(candidates)}')
    source = candidates[0]
    inputs=load_package_inputs(workspace)
    check_package(source, model, image_caps(inputs))
    destination.mkdir(parents=True, exist_ok=False)
    suffix='-EXTREME-DEFAULT-REPARTITION' if inputs.get('partition_layout',{}).get('id','stock')!='stock' else ''
    filename = f'Beyoud-{model}-0.1.0-alpha1{suffix}-UNTESTED.zip'
    output = destination / filename
    try:
        os.link(source, output)  # Avoid doubling a multi-GB package on the same filesystem.
    except OSError:
        shutil.copyfile(source, output)
    digest = hashlib.sha256()
    with output.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    (destination / 'SHA256SUMS').write_text(f'{digest.hexdigest()}  {filename}\n')
    (destination / 'WARNING.txt').write_text(
        f'EXPERIMENTAL UNTESTED ALPHA — {model} ONLY\n'
        'Build success and structural checks DO NOT prove boot or flash safety.\n'
        'May erase data, fail to boot or break calls, camera, encryption and other features.\n'
        'Not for a primary phone. No hardware validation has been performed.\n'
        'Have an independently verified stock recovery procedure and backups before any test.\n')
    if inputs.get('partition_layout',{}).get('id','stock')!='stock':
        (destination/'REQUIRED-PARTITION-LAYOUT.json').write_text(json.dumps(inputs['partition_layout'],indent=2)+'\n')
        with (destination/'WARNING.txt').open('a') as stream:
            stream.write('REQUIRES DEFAULT EXTREMEROM REPARTITION: system 7000 MiB, vendor/product 1500 MiB; ODM 4 MiB, prism 600 MiB, optics 30 MiB. NOT FOR STOCK LAYOUT.\n')
    lock = workspace / 'out/firmware-lock.json'
    if lock.is_file():
        shutil.copyfile(lock, destination / 'firmware-lock.json')
    (destination / 'provenance.json').write_text(json.dumps(marker, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    collect(args.workspace, args.destination)
