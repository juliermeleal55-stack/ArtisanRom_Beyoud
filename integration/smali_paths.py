#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve exact class descriptors across dex directories; never guess by basename."""
from pathlib import Path, PurePosixPath
import re
import sys

DEX = re.compile(r'smali(?:_classes[1-9][0-9]*)?')


def resolve(root, relative):
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or '..' in path.parts or '\\' in relative:
        raise ValueError('Unsafe relative smali path')
    if not path.parts or not DEX.fullmatch(path.parts[0]) or path.suffix != '.smali':
        raise ValueError('Expected dex-relative smali class path')
    suffix = Path(*path.parts[1:])
    descriptor = 'L' + suffix.as_posix()[:-6] + ';'
    found = []
    for dex in sorted(root.iterdir()):
        if not DEX.fullmatch(dex.name) or not dex.is_dir() or dex.is_symlink():
            continue
        candidate = dex / suffix
        if not candidate.exists():
            continue
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()):
            raise ValueError('Unsafe smali class location')
        headers = re.findall(r'(?m)^\.class[^\n]* (L[^\s]+;)\s*$', candidate.read_text())
        if headers != [descriptor]:
            raise ValueError('Class descriptor does not match path: ' + str(candidate))
        found.append(candidate)
    if len(found) != 1:
        raise ValueError(f'Expected exactly one {descriptor}; found {len(found)} in {root}')
    return found[0]


def resolve_apk_path(apktool, relative):
    parts = PurePosixPath(relative).parts
    indexes = [i for i,part in enumerate(parts) if DEX.fullmatch(part)]
    if len(indexes) != 1 or '..' in parts or PurePosixPath(relative).is_absolute():
        raise ValueError('Expected one dex component in decoded APK path')
    index = indexes[0]
    root = apktool.joinpath(*parts[:index])
    if not root.resolve().is_relative_to(apktool.resolve()):
        raise ValueError('Decoded APK escaped root')
    return resolve(root, '/'.join(parts[index:]))


if __name__ == '__main__':
    try:
        root = Path(sys.argv[1])
        if len(sys.argv) == 4 and sys.argv[3] in ('--apktool','--apktool-absolute'):
            result = resolve_apk_path(root, sys.argv[2])
        else:
            result = resolve(root, sys.argv[2])
        print(result if len(sys.argv)==4 and sys.argv[3]=='--apktool-absolute' else result.relative_to(root))
    except (OSError, ValueError) as exc:
        print(f'Smali resolution blocked: {exc}', file=sys.stderr)
        sys.exit(1)
