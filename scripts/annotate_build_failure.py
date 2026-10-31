#!/usr/bin/env python3
"""Expose bounded compiler diagnostics as Actions annotations without signed-log URLs."""
from pathlib import Path
import re
import sys

workspace = Path(sys.argv[1])
paths = sorted((workspace / 'out/beyoud-logs').glob('*.log'))
for path in paths:
    text = re.sub(r'\x1b\[[0-9;]*m', '', path.read_text(errors='replace'))
    # Build logs contain public source URLs; suppress any credential-looking values.
    text = re.sub(r'(?i)(token|password|authorization)([=: ]+)\S+', r'\1\2[REDACTED]', text)
    tail = '\n'.join(text.splitlines()[-45:])[-6000:]
    escaped = tail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print(f'::notice title={path.name}::{escaped}')
