#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed build stages on a persistent Linux filesystem, with resource logs."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integration.targets import from_marker
from integration.samloader.metadata import configured_firmwares
from integration.firmware_check import inspect as inspect_firmware
from integration.package_inputs import atomic_json, retire

STAGES = ('dependencies', 'source', 'target', 'patch', 'retire', 'package')
RESERVE = 2 * 1024**3


def digest_path(path):
    """Content hash, including symlink text, without traversing Android links."""
    digest = hashlib.sha256()
    if not path.exists() and not path.is_symlink():
        raise ValueError(f'Missing checkpoint output: {path}')
    paths = [path]
    if path.is_dir() and not path.is_symlink():
        paths = [path] + sorted(path.rglob('*'))
    for entry in paths:
        if '__pycache__' in entry.parts or entry.suffix == '.pyc':
            continue
        relative = str(entry.relative_to(path)) if entry != path else '.'
        digest.update(relative.encode() + b'\0')
        if entry.is_symlink():
            digest.update(b'L' + os.fsencode(os.readlink(entry)))
        elif entry.is_file():
            digest.update(b'F')
            with entry.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
        elif entry.is_dir():
            digest.update(b'D')
        else:
            raise ValueError(f'Unsupported checkpoint entry: {entry}')
    return digest.hexdigest()


def identity(workspace):
    scopes = ['BEYOUD-WORKSPACE.json', 'buildenv.sh', 'scripts', 'integration',
              'platform', 'target', 'unica', 'security', 'prebuilts',
              'out/firmware-lock.json', 'out/config.sh']
    # Missing optional scopes are represented, never silently confused with data.
    entries = {name: digest_path(workspace / name) if (workspace / name).exists() else None for name in scopes}
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def output_proof(workspace, stage, codename):
    out = workspace / 'out'
    paths = {
        'dependencies': [out / 'tools/bin'],
        'source': [out / 'fw' / '_'.join(item.split('/')[:2]) for item in configured_firmwares(out / 'config.sh', 'source')],
        'target': [out / 'fw' / '_'.join(item.split('/')[:2]) for item in configured_firmwares(out / 'config.sh', 'target')] + [out / 'beyoud-firmware-inspection.json'],
        'patch': [out / 'target' / codename / 'work_dir'],
        'retire': [out / 'beyoud-package-inputs.json', out / 'beyoud-fw-retired.json'],
        'package': sorted(out.glob(f'*alpha1*{codename}*.zip')),
    }[stage]
    if stage == 'retire' and ((out / 'fw').exists() or json.loads(paths[1].read_text()).get('status') != 'retired'):
        raise ValueError('Firmware retirement is incomplete')
    if stage == 'package' and len(paths) != 1:
        raise ValueError('Expected exactly one alpha ZIP; preserve failed outputs and use a fresh workspace if ambiguous')
    if stage == 'patch' and not (paths[0] / '.completed').is_file():
        raise ValueError('Patch stage did not produce .completed')
    if stage == 'dependencies' and (not paths[0].is_dir() or not any(paths[0].iterdir())):
        raise ValueError('No compiled tools')
    proof = {str(path.relative_to(workspace)): digest_path(path) for path in paths}
    if stage == 'dependencies':
        for tool in paths[0].iterdir():
            if tool.is_symlink():
                if not tool.is_file():
                    raise ValueError(f'Dangling/non-file build tool link: {tool}')
                proof[str(tool.relative_to(workspace)) + '::resolved'] = digest_path(tool.resolve())
    return proof


def resources(workspace):
    memory = {}
    info = Path('/proc/meminfo')
    if info.is_file():
        for line in info.read_text().splitlines():
            if line.startswith(('MemTotal:', 'MemAvailable:', 'SwapFree:')):
                key, value, *_ = line.split()
                memory[key.rstrip(':')] = int(value) * 1024
    return dict(time=time.time(), disk_free=shutil.disk_usage(workspace).free, memory=memory)


def environment(workspace, codename, jobs):
    env = dict(os.environ, BEYOUD_JOBS=str(jobs), MAKEFLAGS=f'-j{jobs}',
               CMAKE_BUILD_PARALLEL_LEVEL=str(jobs), CARGO_BUILD_JOBS=str(jobs))
    env.setdefault('JAVA_TOOL_OPTIONS', '-Xmx1024m')
    env.pop('GITHUB_ACTIONS', None)  # Never let ambient CI perform early cleanup.
    stamp = workspace / 'out/beyoud-build-timestamp'
    if not stamp.exists():
        stamp.write_text(str(int(time.time())) + '\n')
    value = stamp.read_text().strip()
    if not value.isdigit():
        raise ValueError('Invalid persisted build timestamp')
    env['BEYOUD_BUILD_TIMESTAMP'] = value
    result = subprocess.run(['bash', '-c', 'set -e; source ./buildenv.sh "$1" >&2; env -0',
                             'beyoud', codename], cwd=workspace, env=env, stdout=subprocess.PIPE, check=True)
    resolved = dict(item.split('=', 1) for item in result.stdout.decode().split('\0') if item)
    _, device = from_marker(json.loads((workspace / 'BEYOUD-WORKSPACE.json').read_text()))
    if resolved.get('TARGET_CODENAME') != codename or resolved.get('TARGET_FIRMWARE', '').split('/')[0] != device['model']:
        raise ValueError('Generated target environment does not match workspace model')
    return resolved


def run_command(command, workspace, env, telemetry, reserve=RESERVE, interval=5):
    """Bounded resource sampling; stop the whole subprocess group before ENOSPC."""
    if shutil.disk_usage(workspace).free < reserve:
        raise ValueError('Insufficient disk reserve before stage launch')
    process = subprocess.Popen(command, cwd=workspace, env=env, start_new_session=True)
    stopped = False
    minimum = None
    try:
        while True:
            sample = resources(workspace)
            minimum = sample['disk_free'] if minimum is None else min(minimum, sample['disk_free'])
            telemetry.write(json.dumps(sample) + '\n')
            telemetry.flush()
            if sample['disk_free'] < reserve and process.poll() is None:
                stopped = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                break
            try:
                process.wait(timeout=interval)
                break
            except subprocess.TimeoutExpired:
                pass
        code = process.wait()
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        raise
    if stopped:
        raise ValueError(f'Stopped to preserve the 2 GiB disk reserve; minimum observed free={minimum}')
    if code != 0:
        raise subprocess.CalledProcessError(code, command)
    return minimum


def validate_prior(workspace, stage, source_id, codename):
    state = workspace / 'out/beyoud-stages'
    prior = STAGES[:STAGES.index(stage)]
    records = {}
    for name in prior:
        path = state / f'{name}.json'
        if not path.is_file():
            raise ValueError(f'Run stage {name} first')
        record = json.loads(path.read_text())
        if record.get('status') != 'success' or record.get('identity') != source_id:
            raise ValueError(f'Stage {name} is failed/stale; use matching sources and rerun from that stage')
        records[name] = record
    retired = 'retire' in records
    if retired and records['retire']['outputs'] != output_proof(workspace, 'retire', codename):
        raise ValueError('Retirement inputs changed')
    for name, record in records.items():
        if name in ('source', 'target') and retired:
            continue  # Retired only after verified patch output and identifier capture.
        if record['outputs'] != output_proof(workspace, name, codename):
            raise ValueError(f'Outputs changed after stage {name}; refusing stale resume')


def package_budget(workspace, codename):
    root = workspace / 'out/target' / codename / 'work_dir'
    sizes = []
    for name in ('system', 'vendor', 'product', 'odm', 'system_ext', 'prism', 'optics',
                 'vendor_dlkm', 'odm_dlkm', 'system_dlkm'):
        path = root / name
        if path.is_dir() and not path.is_symlink():
            sizes.append(sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink()))
    if not sizes:
        raise ValueError('No partition trees for package sizing')
    # Conservative planning estimate: payload + unsigned ZIP + signed ZIP, or
    # accumulated payload plus one image/dat working set. Not a proven bound.
    required = int(max(sum(sizes) * 3.6, sum(sizes) * 1.2 + max(sizes) * 2.4)) + RESERVE
    free = shutil.disk_usage(workspace).free
    print(f'Package planning estimate: free={free}, required={required}', flush=True)
    if free < required:
        raise ValueError('Package estimate exceeds available storage; do not bypass the guard')
    return dict(free=free, estimated_required=required, partition_tree_bytes=sizes)


def execute(workspace, stage, jobs=1):
    if stage not in STAGES or jobs not in range(1, 5):
        raise ValueError('Invalid stage/job budget')
    workspace = workspace.resolve()
    codename, _ = from_marker(json.loads((workspace / 'BEYOUD-WORKSPACE.json').read_text()))
    out = workspace / 'out'
    if out.is_symlink():
        raise ValueError('Workspace out/ must not be a symlink')
    out.mkdir(exist_ok=True)
    state = out / 'beyoud-stages'
    if state.is_symlink():
        raise ValueError('Unsafe stage-state directory')
    state.mkdir(exist_ok=True)
    logs = out / 'beyoud-logs'
    if logs.is_symlink():
        raise ValueError('Unsafe log directory')
    logs.mkdir(exist_ok=True)
    with (state / '.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another build stage is active in this workspace')
        env = environment(workspace, codename, jobs)
        if not (out / 'firmware-lock.json').is_file():
            raise ValueError('Run probe_firmware.sh before build stages')
        source_id = identity(workspace)
        validate_prior(workspace, stage, source_id, codename)
        for name in STAGES[STAGES.index(stage):]:
            (state / f'{name}.json').unlink(missing_ok=True)
        receipt = dict(schema_version=1, stage=stage, codename=codename, identity=source_id,
                       status='running', started=time.time(), before=resources(workspace), jobs=jobs)
        receipt_path = state / f'{stage}.json'
        atomic_json(receipt_path, receipt)
        try:
            if stage == 'retire':
                retire(workspace)
            else:
                if stage == 'package':
                    receipt['package_budget'] = package_budget(workspace, codename)
                command = {
                    'dependencies': ['./scripts/build_dependencies.sh'],
                    'source': [sys.executable, './integration/samloader/stage.py', str(workspace), 'source'],
                    'target': [sys.executable, './integration/samloader/stage.py', str(workspace), 'target'],
                    'patch': ['./scripts/make_rom.sh', '--force', '--no-rom-zip'],
                    'package': ['./scripts/internal/build_flashable_zip.sh'],
                }[stage]
                with (logs / f'resources-{stage}-{time.time_ns()}.jsonl').open('w') as telemetry:
                    receipt['minimum_observed_free'] = run_command(command, workspace, env, telemetry)
                if stage == 'target':
                    inspect_firmware(workspace)
            receipt['outputs'] = output_proof(workspace, stage, codename)
            if identity(workspace) != source_id:
                raise ValueError('Build recipes/configuration changed during stage')
            receipt['status'] = 'success'
        except BaseException as exc:
            receipt.update(status='failed', error=str(exc))
            raise
        finally:
            receipt.update(finished=time.time(), after=resources(workspace))
            atomic_json(receipt_path, receipt)
        print(f'Checkpoint saved: {stage}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    parser.add_argument('stage', choices=STAGES + ('firmware', 'alpha', 'rom'))
    parser.add_argument('--jobs', type=int, choices=range(1, 5), default=1)
    args = parser.parse_args()
    groups = {'alpha': ('source', 'target', 'patch', 'retire', 'package'),
              'rom': ('source', 'target', 'patch'), 'firmware': ('source', 'target')}
    stages = groups.get(args.stage, (args.stage,))
    try:
        for stage in stages:
            execute(args.workspace, stage, args.jobs)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f'Build stage stopped: {exc}', file=sys.stderr)
        sys.exit(1)
