#!/usr/bin/env python3
"""Choose the available filesystem with most free space, without merging or formatting disks."""
import os
from pathlib import Path
import shutil


def choose(default, alternative):
    candidates = [default]
    if alternative.parent.is_dir():
        candidates.append(alternative)
    # Keep the default on ties (including two paths on the same mount).
    return max(candidates, key=lambda path: shutil.disk_usage(path.parent).free)


if __name__ == '__main__':
    default = Path(os.environ['RUNNER_TEMP']) / 'beyoud-workspace'
    alternative = Path('/mnt') / f'beyoud-{os.environ["GITHUB_RUN_ID"]}' / 'workspace'
    selected = choose(default, alternative)
    if selected.exists():
        raise SystemExit('Selected workspace already exists; refusing to overwrite it')
    print(f'Workspace selected: {selected}; free={shutil.disk_usage(selected.parent).free} bytes')
    with open(os.environ['GITHUB_ENV'], 'a') as env:
        env.write(f'WORKSPACE={selected}\n')
