#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Register-independent port of Artisan's Freecess model-property correction."""
from pathlib import Path
import re
import sys

CLASS = 'Lcom/android/server/am/FreecessController;'
OLD = 'ro.product.model'
NEW = 'ro.product.vendor.model'
TRIVIA = r'(?:[ \t]*(?:\r?\n|#[^\n]*\n|\.line[^\n]*\n|\.local[^\n]*\n|\.end local[^\n]*\n))*'


def reads(text, property_name):
    pattern = (r'(?m)^[ \t]*const-string(?:/jumbo)?[ \t]+(?P<reg>[vp]\d+),[ \t]*"'
               + re.escape(property_name) + r'"[ \t]*(?:#[^\n]*)?\r?\n' + TRIVIA
               + r'[ \t]*invoke-static(?:/range)?[ \t]+\{(?P<args>[^}\n]+)\},[ \t]*'
               + r'Landroid/os/SystemProperties;->get\((?P<signature>Ljava/lang/String;(?:Ljava/lang/String;)?)\)Ljava/lang/String;')
    result = []
    for match in re.finditer(pattern, text):
        args = match['args'].strip()
        reg = match['reg']
        if match['signature'] == 'Ljava/lang/String;':
            valid = args == reg or re.fullmatch(re.escape(reg) + r'\s*\.\.\s*' + re.escape(reg), args)
        else:
            valid = re.fullmatch(re.escape(reg) + r'\s*,\s*[vp]\d+', args)
        if valid:
            result.append(match)
    return result


def adapt(text):
    if not re.search(r'(?m)^\.class[^\n]* ' + re.escape(CLASS) + r'\s*$', text):
        raise ValueError('Unexpected Freecess class descriptor')
    old, new = reads(text, OLD), reads(text, NEW)
    if not old and len(new) == 1:
        return text, 'already-adapted'
    if len(old) != 1 or new:
        raise ValueError(f'Expected one unambiguous Freecess property read; found old={len(old)}, vendor={len(new)}')
    match = old[0]
    # Require a method body; do not reinterpret fields, comments or metadata.
    before = text[:match.start()]
    if before.rfind('.method ') <= before.rfind('.end method') or text.find('.end method', match.end()) < 0:
        raise ValueError('Freecess property read is not inside a complete method')
    segment = text[match.start():match.end()]
    changed = segment.replace(f'"{OLD}"', f'"{NEW}"', 1)
    return text[:match.start()] + changed + text[match.end():], 'adapted'


def apply(apk_root):
    paths = list(apk_root.rglob('FreecessController.smali'))
    if len(paths) != 1 or not paths[0].resolve().is_relative_to(apk_root.resolve()):
        raise ValueError('Expected exactly one FreecessController inside decoded services.jar')
    path = paths[0]
    original = path.read_text()
    try:
        text, status = adapt(original)
    except ValueError:
        # Bounded actual-donor context survives in log annotations on failure.
        lines = original.splitlines()
        for index, line in enumerate(lines):
            if 'ro.product.' in line:
                print('\n'.join(lines[max(0, index-5):index+10]), file=sys.stderr)
        raise
    if text != original:
        path.write_text(text)
    print(f'Freecess model detection: {status}; {path}', flush=True)


if __name__ == '__main__':
    try:
        apply(Path(sys.argv[1]))
    except (OSError, ValueError) as exc:
        print(f'Freecess adaptation blocked: {exc}', file=sys.stderr)
        sys.exit(1)
