#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retain Artisan's no-seamless-threshold fix without donor numbers/registers."""
from pathlib import Path
import re
import sys

CLASS = 'Lcom/samsung/android/hardware/display/RefreshRateConfig;'
THRESHOLD = CLASS[:-1] + '$BrightnessThreshold;'
STRING = re.compile(r'^\s*const-string(?:/jumbo)?\s+([vp]\d+),\s*"([^"\\]*)"\s*(?:#.*)?$')
NUMBERS = re.compile(r'(?:\d+(?:\.\d+)?(?:,\d+(?:\.\d+)?)*)?')


def adapt(text):
    if not re.search(r'(?m)^\.class[^\n]* ' + re.escape(CLASS) + r'\s*$', text):
        raise ValueError('Unexpected RefreshRateConfig descriptor')
    method = re.compile(r'(?ms)^\.method[^\n]* static [^\n]*getMainInstance\(\)' +
                        re.escape(CLASS) + r'\s*\n.*?^\.end method\s*$')
    methods = list(method.finditer(text))
    if len(methods) != 1:
        raise ValueError('Expected one static getMainInstance()')
    match = methods[0]
    lines = match[0].splitlines(keepends=True)
    calls = [(i, re.fullmatch(r'\s*invoke-direct\s+\{([^}]+)\},\s*' + re.escape(THRESHOLD) +
                            r'-><init>\((?:Ljava/lang/String;){4}\)V\s*', line))
             for i, line in enumerate(lines)]
    calls = [(i, call) for i, call in calls if call]
    if len(calls) != 1:
        raise ValueError('Expected one four-string BrightnessThreshold constructor')
    index, call = calls[0]
    regs = [reg.strip() for reg in call[1].split(',')]
    if len(regs) != 5 or any(not re.fullmatch(r'[vp]\d+', r) for r in regs):
        raise ValueError('Unsupported threshold argument registers')
    defaults, properties = regs[1:3], regs[3:5]
    if set(defaults) & set(properties + regs[:1]) or len(set(properties)) != 2:
        raise ValueError('Threshold defaults alias property/receiver registers')
    # Interpret only a straight-line constant initialization segment. Do not
    # guess across branches, field reads, calls, or register reassignments.
    found = {}
    for i in range(index - 1, -1, -1):
        line = lines[i].strip()
        if not line or line.startswith(('#', '.line ')):
            continue
        definition = STRING.fullmatch(line)
        if not definition:
            break
        found.setdefault(definition[1], (i, definition[2]))
    expected = ['persist.dm.passive.display_brightness', 'persist.dm.passive.ambient_brightness']
    if any(reg not in found for reg in regs[1:]) or [found[r][1] for r in properties] != expected:
        raise ValueError('Threshold property/default data flow changed')
    for reg in set(defaults):
        i, value = found[reg]
        if not NUMBERS.fullmatch(value):
            raise ValueError('Non-numeric threshold default; manual review required')
        lines[i] = lines[i].replace('"' + value + '"', '""', 1)
    changed = text[:match.start()] + ''.join(lines) + text[match.end():]
    # These are diagnostic strings only; preserve the historical cosmetic fix
    # where present, without requiring Samsung to keep the same dump method.
    for label in ('SEAMLESS_BRT', 'SEAMLESS_LUX'):
        pattern = re.compile(r'(?m)^(\s*const-string(?:/jumbo)?\s+[vp]\d+,\s*")' + label + r': ([^"\n]*)("[^\n]*)$')
        markers = list(pattern.finditer(changed))
        if len(markers) > 1 or any(not NUMBERS.fullmatch(m[2]) for m in markers):
            raise ValueError('Ambiguous/non-numeric ' + label + ' diagnostic')
        changed = pattern.sub(lambda m: m[1] + label + ': ' + m[3], changed)
    return changed


def apply(root):
    paths = list(root.rglob('RefreshRateConfig.smali'))
    if len(paths) != 1 or paths[0].is_symlink() or not paths[0].resolve().is_relative_to(root.resolve()):
        raise ValueError('Expected exactly one RefreshRateConfig inside framework.jar')
    path = paths[0]
    original = path.read_text()
    try:
        changed = adapt(original)  # All checks complete before writing anything.
    except ValueError:
        # Bounded ACTUAL donor context is accessible via Actions annotations,
        # not just the stale search context printed by git apply.
        lines = original.splitlines()
        selected = set()
        for i, line in enumerate(lines):
            if 'getMainInstance()' in line or 'BrightnessThreshold;-><init>' in line or 'SEAMLESS_' in line:
                selected.update(range(max(0, i-8), min(len(lines), i+12)))
        print('Actual RefreshRateConfig context:\n' + '\n'.join(lines[i] for i in sorted(selected))[:5000], file=sys.stderr)
        raise
    if changed != original:
        path.write_text(changed)
    print('RefreshRateConfig: verified empty brightness/lux defaults', flush=True)


if __name__ == '__main__':
    try:
        apply(Path(sys.argv[1]))
    except (OSError, ValueError) as exc:
        print(f'Refresh-rate adaptation blocked: {exc}', file=sys.stderr)
        sys.exit(1)
