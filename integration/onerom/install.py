# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned text verification and explicit, non-overwriting compatibility overlay."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
MODULES = ('search_indexing', 'usb_initialization', 'wallpaper_capture', 'user_defaults')


def verify():
    manifest = json.loads((ROOT / 'manifests/onerom.json').read_text())
    source = ROOT / 'integration/onerom/upstream'
    for entry in manifest['files']:
        path = source / entry['path']
        if not path.resolve().is_relative_to(source.resolve()):
            raise ValueError('Unsafe OneROM manifest path')
        data = path.read_bytes()
        sha = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if sha != entry['sha'] or len(data) != entry['size']:
            raise ValueError(f'Modified OneROM reference: {entry["path"]}')
    return manifest


def bluetooth_policy(text):
    apex = 'ADD_TO_WORK_DIR "b0sxxx" "system" "system/apex/com.android.bt.apex" 0 0 644 "u:object_r:system_file:s0"'
    anchor = '# BT-lib-patch\n'
    if text.count(apex) != 1 or text.count(anchor) != 1 or not text.rstrip().endswith('"289767394805003736008052" "289767392a00001436008052"'):
        raise ValueError('Unexpected legacy Bluetooth patch; manual review required')
    probe = '_BEYOUD_BT_API=$(python3 "$SRC_DIR/integration/onerom/compat.py" sdk "$FW_DIR" "$SOURCE_FIRMWARE") || return 1\n'
    text = text.replace(apex, probe + 'if (( _BEYOUD_BT_API < 37 )); then\n' + apex + '\nfi')
    text = text.replace(anchor, anchor + 'if (( _BEYOUD_BT_API < 37 )); then\n')
    return text.rstrip() + '\nfi\n'


def install(workspace, codename):
    if codename not in ('beyond1lte', 'beyond2lte'):
        raise ValueError('Unsupported OneROM overlay target')
    manifest = verify()
    miscs = workspace / 'platform/exynos9820/patches/miscs/customize.sh'
    patched = bluetooth_policy(miscs.read_text())
    plan = [(ROOT / 'integration/onerom/legacy_init', workspace / 'platform/exynos9820/patches/zz_beyoud_legacy_init')]
    if codename == 'beyond1lte':
        for module in MODULES:
            relative = Path('target/beyond1lte/patches') / module
            source = ROOT / 'integration/onerom/upstream' / relative
            if not (source / 'disable').is_file():
                raise ValueError('Candidate must retain upstream disable marker')
            plan.append((source, workspace / relative))
    if any(destination.exists() for _, destination in plan):
        raise ValueError('Refusing to overwrite existing compatibility modules')
    for source, destination in plan:
        shutil.copytree(source, destination)
    miscs.write_text(patched)
    return {'repository': manifest['repository'], 'commit': manifest['commit'],
            'active': ['actual-donor-SDK-gated legacy Bluetooth replacement', 'guarded legacy vendor initialization'],
            'disabled_candidates': list(MODULES) if codename == 'beyond1lte' else []}
