#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Preserve CoreRune vendor identity substitutions without fixed dex/registers."""
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from freecess import reads

CLASS = 'Lcom/samsung/android/rune/CoreRune;'


def adapt(text, descriptor=CLASS, substitutions=None):
    if not re.search(r'(?m)^\.class[^\n]* ' + re.escape(descriptor) + r'\s*$', text):
        raise ValueError('Unexpected CoreRune class')
    changes = []
    substitutions = substitutions or [('ro.product.device', 'ro.product.vendor.device'), ('ro.product.model', 'ro.product.vendor.model')]
    for old, new in substitutions:
        key = old
        before, after = reads(text, old), reads(text, new)
        if not before and len(after) == 1:
            continue
        if len(before) != 1 or after:
            raise ValueError(f'Ambiguous CoreRune {key} read: old={len(before)}, vendor={len(after)}')
        match = before[0]
        prefix = text[:match.start()]
        if prefix.rfind('.method ') <= prefix.rfind('.end method') or text.find('.end method', match.end()) < 0:
            raise ValueError('CoreRune identity read outside a method')
        changes.append((match.start(), match.end(), match.group().replace(f'"{old}"', f'"{new}"', 1)))
    for start, end, replacement in sorted(changes, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def apply(root, filename="CoreRune.smali", descriptor=CLASS, substitutions=None):
    files = list(root.rglob(filename))
    if len(files) != 1 or not files[0].resolve().is_relative_to(root.resolve()):
        raise ValueError('Expected exactly one decoded CoreRune class')
    path = files[0]
    original = path.read_text()
    result = adapt(original, descriptor, substitutions)  # Both edits validated before writing either.
    if result != original:
        path.write_text(result)
    print(f'CoreRune device/model detection: verified vendor reads; {path}', flush=True)


if __name__ == '__main__':
    try:
        apply(Path(sys.argv[1]))
    except (OSError, ValueError) as exc:
        print(f'CoreRune adaptation blocked: {exc}', file=sys.stderr)
        sys.exit(1)
