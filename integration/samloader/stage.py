#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Download -> extract -> verify marker -> remove Odin packages, one firmware at a time."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

from metadata import get, configured_firmwares


def prepare(workspace):
    workspace = workspace.resolve()
    if not (workspace / 'BEYOUD-WORKSPACE.json').is_file():
        raise ValueError('Not a generated workspace')
    out = workspace / 'out'
    lock = out / 'firmware-lock.json'
    env = dict(os.environ, SRC_DIR=str(workspace), OUT_DIR=str(out),
               ODIN_DIR=str(out / 'odin'), FW_DIR=str(out / 'fw'), TOOLS_DIR=str(out / 'tools'))
    # Keep original extractor cleanup disabled: only this orchestrator removes packages,
    # after checking the version-specific successful extraction marker.
    env.pop('GITHUB_ACTIONS', None)
    seen = set()
    for descriptor in configured_firmwares(out / 'config.sh'):
        model, csc, *_ = descriptor.split('/')
        if (model, csc) in seen:
            continue
        seen.add((model, csc))
        record = get(lock, model, csc)
        extracted = out / 'fw' / f'{model}_{csc}'
        odin = out / 'odin' / f'{model}_{csc}'
        marker = extracted / '.extracted'
        if marker.exists():
            if marker.read_text().strip() != record['version']:
                raise ValueError(f'Extracted version differs from lock for {model}/{csc}; use a fresh workspace')
        else:
            free = shutil.disk_usage(workspace).free
            required = record['size'] + 8 * 1024**3
            print(f'Sequential firmware {model}/{csc}: free={free}, download minimum={required}', flush=True)
            if free < required:
                raise ValueError(f'Not enough space for the next firmware: {model}/{csc}')
            for script in ('download_fw.sh', 'extract_fw.sh'):
                subprocess.run([str(workspace / 'scripts' / script), '--ignore-source', '--ignore-target', descriptor],
                               check=True, env=env)
            if not marker.is_file() or marker.read_text().strip() != record['version']:
                raise ValueError(f'Extractor did not confirm the locked version for {model}/{csc}')
        if not any(child.is_dir() for child in extracted.iterdir()):
            raise ValueError(f'Extraction marker has no extracted content: {model}/{csc}')
        # Fixed model/CSC validated by metadata.get; never remove fw/ or source artifacts.
        if odin.exists():
            if odin.is_symlink() or odin.resolve().parent != (out / 'odin').resolve():
                raise ValueError('Unsafe Odin cleanup path')
            shutil.rmtree(odin)
        print(f'Extraction verified for {model}/{csc}; Odin packages released. Free={shutil.disk_usage(workspace).free}', flush=True)


if __name__ == '__main__':
    try:
        prepare(Path(sys.argv[1]))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f'Sequential firmware preparation failed: {exc}', file=sys.stderr)
        sys.exit(1)
