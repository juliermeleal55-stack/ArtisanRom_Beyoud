#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Remove only obsolete rounded-corner overlay resources, allowing prior absence."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def prune(root):
    res=root/'res'
    if not res.is_dir() or res.is_symlink():raise ValueError('Missing/unsafe decoded overlay resources')
    plans={}
    for name in ('bools.xml','public.xml'):
        path=res/'values'/name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):raise ValueError('Unsafe overlay XML')
        if not path.exists():continue
        original=path.read_bytes()
        tree=ET.fromstring(original,parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
        if tree.tag!='resources':raise ValueError('Unexpected Android resources root')
        removed=False
        for child in list(tree):
            kind=child.get('type') if child.tag in ('public','item') else child.tag
            if (kind,child.get('name')) in {('bool','config_enableRoundedCorner'),('drawable','rounded')}:
                tree.remove(child);removed=True
        if removed:plans[path]=ET.tostring(tree,encoding='utf-8',xml_declaration=True)+b'\n'
    rounded=res/'drawable/rounded.xml'
    if rounded.is_symlink() or not rounded.resolve().is_relative_to(root.resolve()):raise ValueError('Unsafe rounded drawable')
    for path,data in plans.items():path.write_bytes(data)
    rounded.unlink(missing_ok=True)
    print('SystemUI RRO: obsolete rounded-corner entries removed or already absent',flush=True)


if __name__=='__main__':
    try:prune(Path(sys.argv[1]))
    except (OSError,ValueError,ET.ParseError) as exc:
        print(f'Overlay adaptation blocked: {exc}',file=sys.stderr);sys.exit(1)
