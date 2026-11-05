#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Collect donor patch mismatches in diagnostic-only runs; never approve a partial run."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def logdir(workspace):
    return workspace / 'out/beyoud-logs'


def start(workspace):
    directory = logdir(workspace)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'patch-preflight.jsonl').write_text('')
    (directory / 'patch-preflight.json').unlink(missing_ok=True)
    record(workspace, dict(kind='start', status='running'))


def record(workspace, event):
    path = logdir(workspace) / 'patch-preflight.jsonl'
    # A collector cannot silently start midway through a real build.
    if not path.is_file():
        raise ValueError('Patch preflight was not initialized by the controller')
    with path.open('a') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(json.dumps(event) + '\n')
        stream.flush()


def relative(workspace, path):
    return str(path.resolve().relative_to(workspace.resolve()))


def apply(workspace, decoded, patch):
    if not (logdir(workspace) / 'patch-preflight.jsonl').is_file():
        raise ValueError('Patch preflight was not initialized by the controller')
    relative(workspace, decoded)
    name = relative(workspace, patch)
    text = patch.read_text()
    targets = []
    for target in re.findall(r'(?m)^\+\+\+ b/(.+)$', text):
        path = decoded / target
        if not path.resolve().is_relative_to(decoded.resolve()) or path.is_symlink():
            raise ValueError('Unsafe patch target')
        targets.append(path)
    if not targets:
        raise ValueError('No patch targets')
    hashes = {relative(workspace, p): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in targets if p.is_file()}
    command = ['git', 'apply', '--directory=' + str(decoded), '--unsafe-paths', '--verbose']
    # Git applies atomically without --reject. Preserve sequential dependencies
    # for successful patches, but do not mutate a target when check fails.
    checked = subprocess.run(command + ['--check', str(patch)], cwd=workspace, capture_output=True, text=True)
    result = checked if checked.returncode else subprocess.run(command + [str(patch)], cwd=workspace, capture_output=True, text=True)
    event = dict(kind='patch', patch=name, status='failed' if result.returncode else 'passed',
                 inputs=hashes, detail=(result.stderr + result.stdout)[-6000:])
    if result.returncode:
        saved = logdir(workspace) / 'patch-preflight-smali'
        total = sum(p.stat().st_size for p in saved.rglob('*.smali')) if saved.exists() else 0
        for path in targets:
            if path.is_file() and path.suffix == '.smali' and path.stat().st_size <= 1024**2 and total + path.stat().st_size <= 16 * 1024**2:
                dest = saved / hashlib.sha256(name.encode()).hexdigest()[:16] / path.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
                total += path.stat().st_size
    record(workspace, event)
    print(f'PREFLIGHT {event["status"]}: {name}', flush=True)
    if result.returncode:
        print(event['detail'], flush=True)
    # Only this explicitly diagnostic caller collects onward. finish() fails
    # the entire stage before any APK/kernel/package is built if ANY failed.


def module(workspace, path, status, log):
    record(workspace, dict(kind='module', module=relative(workspace, path), status=status,
                           detail=log.read_text(errors='replace')[-2000:]))


def finish(workspace):
    path = logdir(workspace) / 'patch-preflight.jsonl'
    events = [json.loads(line) for line in path.read_text().splitlines()]
    failures = [e for e in events if e['status'] == 'failed']
    modules = [e for e in events if e['kind'] == 'module']
    patches = [e for e in events if e['kind'] == 'patch']
    marker = json.loads((workspace / 'BEYOUD-WORKSPACE.json').read_text())
    expected_roots = {name for name in ('unica/patches', 'platform/' + os.environ.get('TARGET_PLATFORM', 'exynos9820') + '/patches',
                      'target/' + marker['codename'] + '/patches', 'unica/mods') if (workspace / name).is_dir()}
    roots = [e['root'] for e in events if e['kind'] == 'root']
    if not expected_roots or set(roots) != expected_roots or len(roots) != len(expected_roots):
        failures.append(dict(kind='coverage', status='failed', detail='Missing/duplicate module-root traversal'))
    if not events or events[0].get('kind') != 'start' or not modules or not patches:
        failures.append(dict(kind='coverage', status='failed', detail='Incomplete/empty module or patch traversal'))
    report = dict(schema_version=1, status='blocked' if failures else 'passed',
                  scope='executed conditional paths; not boot/native runtime validation',
                  kernel='deferred to real build',
                  warning='Later mismatches may depend on earlier failures; failed modules have incomplete coverage.',
                  modules=len(modules), patches=len(patches), failures=failures, events=events)
    (logdir(workspace) / 'patch-preflight.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Patch preflight: {len(modules)} modules, {len(patches)} patch attempts, {len(failures)} failures', flush=True)
    if failures:
        summary = '\n'.join(e.get('patch', e.get('module', 'coverage')) + ': ' + e.get('detail', '')[:500] for e in failures)
        summary = summary[:28000].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print(f'::error title=Patch preflight blocked; no ROM built::{summary}', flush=True)
        raise ValueError('Donor patch preflight failed; refusing kernel/APK/ROM build')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'module-passed', 'module-failed', 'root', 'finish'))
    parser.add_argument('workspace', type=Path)
    parser.add_argument('paths', nargs='*', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'apply':
            apply(args.workspace, *args.paths)
        elif args.action == 'root':
            record(args.workspace, dict(kind='root', root=relative(args.workspace, args.paths[0]), status='passed'))
        elif args.action.startswith('module-'):
            module(args.workspace, args.paths[0], args.action.split('-')[1], args.paths[1])
        else:
            finish(args.workspace)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        print(f'Patch preflight blocked: {exc}', file=sys.stderr)
        sys.exit(1)
