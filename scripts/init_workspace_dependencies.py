#!/usr/bin/env python3
"""Initialize exact historical submodule revisions in a generated workspace."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    workspace = parser.parse_args().workspace.resolve()
    if not (workspace / 'BEYOUD-WORKSPACE.json').is_file():
        parser.error('Not a generated candidate workspace')
    for entry in json.loads((ROOT / 'manifests/artisan-submodules.json').read_text()):
        path = workspace / entry['path']
        if path.exists() and any(path.iterdir()):
            parser.error(f'{path} is not empty; refusing to overwrite')
        subprocess.run(['git', 'init', str(path)], check=True)
        subprocess.run(['git', '-C', str(path), 'remote', 'add', 'origin', entry['url']], check=True)
        subprocess.run(['git', '-C', str(path), 'fetch', '--depth=1', 'origin', entry['commit']], check=True)
        subprocess.run(['git', '-C', str(path), 'checkout', '--detach', entry['commit']], check=True)
        subprocess.run(['git', '-C', str(path), 'submodule', 'update', '--init', '--recursive', '--depth=1'], check=True)


if __name__ == '__main__':
    main()
