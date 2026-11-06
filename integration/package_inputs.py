#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Preserve only ZIP fingerprint identifiers before retiring extracted firmware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import struct
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integration.samloader.metadata import configured_firmwares, get
from integration.targets import from_marker


def lock_digest(workspace):
    return hashlib.sha256((workspace / 'out/firmware-lock.json').read_bytes()).hexdigest()


def atomic_json(path, data):
    temporary = path.with_suffix('.partial')
    with temporary.open('w') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def read_prop(path, key, aliases=(), fingerprint_keys=()):
    """Resolve real firmware properties, never invent a device from a model name.

    Malformed/duplicate preferred properties are errors, not reasons to fall
    through to another key. Android partition-scoped aliases are used only
    when the legacy property is absent.
    """
    props = {}
    for line in path.read_text().splitlines():
        if line.lstrip().startswith('#') or '=' not in line:
            continue
        name, _, value = line.partition('=')
        props.setdefault(name.strip(), []).append(value.strip())
    for name in (key, *aliases):
        if name not in props:
            continue
        values = props[name]
        if len(values) != 1 or not re.fullmatch(r'[A-Za-z0-9_.-]+', values[0]):
            raise ValueError(f'Invalid/ambiguous package identifier {name} in {path}')
        return values[0]
    # A standard Android fingerprint is brand/product/device:release/id/
    # incremental:type/tags. Only its device component is an equivalent here.
    token = r'[A-Za-z0-9_.-]+'
    pattern = rf'{token}/{token}/({token}):{token}/{token}/{token}:{token}/{token}'
    for name in fingerprint_keys:
        if name not in props:
            continue
        values = props[name]
        match = re.fullmatch(pattern, values[0]) if len(values) == 1 else None
        if not match:
            raise ValueError(f'Invalid/ambiguous firmware fingerprint {name} in {path}')
        return match.group(1)
    tried = ', '.join((key, *aliases, *fingerprint_keys))
    raise ValueError(f'Missing package identifier in {path}; tried {tried}')


def capture(workspace):
    codename, device = from_marker(json.loads((workspace / 'BEYOUD-WORKSPACE.json').read_text()))
    descriptors = list(configured_firmwares(workspace / 'out/config.sh'))
    if len(descriptors) < 2:
        raise ValueError('Expected source and target descriptors')
    ids = {}
    for role, descriptor in zip(('source', 'target'), descriptors[:2]):
        model, csc, *_ = descriptor.split('/')
        record = get(workspace / 'out/firmware-lock.json', model, csc)
        if role == 'target' and model != device['model']:
            raise ValueError('Target firmware does not match selected device')
        root = workspace / 'out/fw' / f'{model}_{csc}'
        if root.is_symlink() or not root.resolve().is_relative_to(workspace.resolve()):
            raise ValueError('Unsafe extracted firmware root')
        if not (root / '.extracted').is_file() or (root / '.extracted').read_text().strip() != record['version']:
            raise ValueError('Package identifiers require the locked extracted firmware')
        for suffix, relative, key in [('product', 'system/system/build.prop', 'ro.build.product'),
                                      ('vendor', 'vendor/build.prop', 'ro.product.vendor.device')]:
            path = root / relative
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Unsafe firmware property path')
            aliases = ('ro.product.system.device', 'ro.product.device') if suffix == 'product' else ('ro.product.device',)
            fingerprints = ('ro.system.build.fingerprint', 'ro.build.fingerprint') if suffix == 'product' else ('ro.vendor.build.fingerprint',)
            ids[f'{role}_{suffix}'] = read_prop(path, key, aliases, fingerprints)
    target_model, target_csc, *_ = descriptors[1].split('/')
    metadata = workspace / 'out/fw' / f'{target_model}_{target_csc}' / 'os_partitions_metadata.txt'
    pairs = re.findall(r'^([a-z_]+)_size=([0-9]+)$', metadata.read_text(), re.M)
    limits = {name: int(size) for name, size in pairs}
    if len(limits) != len(pairs) or any(size <= 0 for size in limits.values()) or not {'system', 'vendor'} <= limits.keys():
        raise ValueError('Missing/ambiguous stock image size limits')
    return dict(schema_version=1, codename=codename, model=device['model'],
                firmware_lock_sha256=lock_digest(workspace), identifiers=ids,
                stock_image_size_caps=limits)


def load(workspace):
    cache = workspace / 'out/beyoud-package-inputs.json'
    data = json.loads(cache.read_text()) if cache.is_file() else capture(workspace)
    codename, device = from_marker(json.loads((workspace / 'BEYOUD-WORKSPACE.json').read_text()))
    if (data.get('schema_version') != 1 or data.get('codename') != codename or data.get('model') != device['model']
            or data.get('firmware_lock_sha256') != lock_digest(workspace)):
        raise ValueError('Package identifiers do not match workspace/firmware lock')
    return data


def identifier(workspace, key):
    value = load(workspace)['identifiers'][key]
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
        raise ValueError('Invalid cached package identifier')
    return value


def check_image(workspace, partition, image):
    data = load(workspace)
    cap = data['stock_image_size_caps'].get(partition)
    if type(cap) is not int or cap <= 0:
        raise ValueError(f'No verified stock image size cap for {partition}')
    with image.open('rb') as stream:
        header = stream.read(28)
    if len(header) >= 4 and struct.unpack('<I', header[:4])[0] == 0xED26FF3A:
        if len(header) != 28:
            raise ValueError('Truncated sparse image header')
        _, major, _, file_header, chunk_header, block, blocks, _, _ = struct.unpack('<I4H4I', header)
        if major != 1 or file_header < 28 or chunk_header < 12 or block <= 0 or block % 4 or blocks <= 0:
            raise ValueError('Invalid sparse image dimensions')
        logical = block * blocks
    else:
        logical = image.stat().st_size
    if logical <= 0 or logical > cap:
        raise ValueError(f'{partition} logical image size={logical} exceeds stock image cap={cap}; revise payload, do not bypass')
    print(f'{partition}: logical bytes={logical}, stock image cap={cap} (not a physical partition-table certification)', flush=True)


def retire(workspace):
    workspace = workspace.resolve()
    out = workspace / 'out'
    fw = out / 'fw'
    tombstone = out / 'beyoud-fw-retired.json'
    if tombstone.exists():
        raise ValueError('Firmware retirement already started; resume at package after success, otherwise use a fresh workspace')
    if out.is_symlink() or fw.is_symlink() or fw.resolve().parent != out.resolve() or not fw.is_dir():
        raise ValueError('Unsafe firmware retirement root')
    descriptors = list(configured_firmwares(out / 'config.sh'))
    expected = set()
    for descriptor in descriptors:
        model, csc, *_ = descriptor.split('/')
        record = get(out / 'firmware-lock.json', model, csc)
        expected.add(f'{model}_{csc}')
        marker = fw / f'{model}_{csc}' / '.extracted'
        if marker.parent.is_symlink() or not marker.is_file() or marker.read_text().strip() != record['version']:
            raise ValueError('Cannot retire incomplete/mismatched firmware')
    if set(path.name for path in fw.iterdir()) != expected:
        raise ValueError('Unexpected firmware directories; refusing broad cleanup')
    mounts = Path('/proc/self/mountinfo')
    if not mounts.is_file():
        raise ValueError('Linux mount validation unavailable')
    for line in mounts.read_text().splitlines():
        mount = line.split()[4]
        for escaped, plain in [('\\040', ' '), ('\\011', '\t'), ('\\134', '\\')]:
            mount = mount.replace(escaped, plain)
        if Path(mount) == fw or fw in Path(mount).parents:
            raise ValueError('Refusing to delete mounted firmware')
    data = capture(workspace)
    atomic_json(out / 'beyoud-package-inputs.json', data)
    # Crash marker is written BEFORE destructive deletion. Earlier extraction
    # stages must never trust a half-deleted .extracted tree after interruption.
    atomic_json(tombstone, dict(status='retiring', firmware_lock_sha256=lock_digest(workspace)))
    shutil.rmtree(fw)
    atomic_json(tombstone, dict(status='retired', firmware_lock_sha256=lock_digest(workspace)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('get', 'verify', 'check-image', 'retire'))
    parser.add_argument('workspace', type=Path)
    parser.add_argument('key', nargs='?')
    parser.add_argument('image', type=Path, nargs='?')
    args = parser.parse_args()
    if args.command == 'get':
        print(identifier(args.workspace, args.key))
    elif args.command == 'verify':
        for key in ('source_product', 'source_vendor', 'target_product', 'target_vendor'):
            identifier(args.workspace, key)
        print(json.dumps(load(args.workspace), indent=2))
    elif args.command == 'check-image':
        check_image(args.workspace, args.key, args.image)
    else:
        retire(args.workspace)
