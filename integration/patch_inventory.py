# SPDX-License-Identifier: GPL-3.0-or-later
"""Inventory effective modules and brittle native/smali sites; not compatibility certification."""
import json
from pathlib import Path


def inventory(workspace, codename, env):
    platform = env.get('TARGET_PLATFORM', 'exynos9820')
    image = env.get('TARGET_SINGLE_SYSTEM_IMAGE', '')
    roots = ('unica/patches', f'platform/{platform}/patches', f'target/{codename}/patches', 'unica/mods')
    modules = []
    for relative in roots:
        root = workspace / relative
        if not root.is_dir():
            continue
        for module in sorted(root.iterdir()):
            if not module.is_dir():
                continue
            effective = module / image if image and (module / image).is_dir() else module
            if not (effective / 'module.prop').is_file():
                continue
            disabled = (effective / 'disable').is_file()
            entry = dict(path=str(effective.relative_to(workspace)), disabled=disabled,
                         smali_patches=[], native_patch_scripts=[], ignored_failure_sites=[])
            for file in sorted(effective.rglob('*')):
                if not file.is_file() or file.is_symlink():
                    continue
                if file.suffix == '.patch':
                    entry['smali_patches'].append(str(file.relative_to(workspace)))
                elif file.suffix == '.sh':
                    text = file.read_text(errors='replace')
                    if 'HEX_PATCH' in text:
                        entry['native_patch_scripts'].append(str(file.relative_to(workspace)))
                    for number, line in enumerate(text.splitlines(), 1):
                        if '|| LOGW' in line or '|| true' in line:
                            entry['ignored_failure_sites'].append(dict(file=str(file.relative_to(workspace)), line=number))
            modules.append(entry)
    result = dict(schema_version=1, codename=codename, status='inventory-only-not-donor-validated', modules=modules)
    destination = workspace / 'out/beyoud-logs/patch-inventory.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Patch inventory: {sum(not m["disabled"] for m in modules)} active modules; donor-specific patch applicability remains unvalidated', flush=True)
    return result
