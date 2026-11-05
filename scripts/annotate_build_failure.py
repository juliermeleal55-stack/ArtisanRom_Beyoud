#!/usr/bin/env python3
"""Expose bounded compiler diagnostics as Actions annotations without signed-log URLs."""
from pathlib import Path
import re
import shutil
import sys

workspace = Path(sys.argv[1])
paths = sorted((workspace / 'out/beyoud-logs').glob('*.log'))
for path in paths:
    text = re.sub(r'\x1b\[[0-9;]*m', '', path.read_text(errors='replace'))
    # Build logs contain public source URLs; suppress any credential-looking values.
    text = re.sub(r'(?i)(token|password|authorization)([=: ]+)\S+', r'\1\2[REDACTED]', text)
    # Preserve bounded actual donor smali behind failed git-apply sites. This
    # avoids guessing from an old patch's search context on the next revision.
    decoded = (workspace / 'out/target').resolve()
    for value in set(re.findall(r'error: (?:patch failed: )?(/[^:\n]+\.smali)', text)):
        source = Path(value)
        if (source.is_file() and not source.is_symlink()
                and source.resolve().is_relative_to(decoded) and source.stat().st_size <= 2 * 1024**2):
            destination = workspace / 'out/beyoud-logs/failed-smali' / source.resolve().relative_to(decoded)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    tail = '\n'.join(text.splitlines()[-45:])[-6000:]
    escaped = tail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print(f'::notice title={path.name}::{escaped}')
