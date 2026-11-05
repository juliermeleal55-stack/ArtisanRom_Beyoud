#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Preserve bounded failed native inputs privately; never modify or skip a patch."""
import hashlib
import json
from pathlib import Path
import shutil
import sys


def capture(workspace,path,old,new):
    allowed=(workspace/'out/target').resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(allowed):raise ValueError('Unsafe native input')
    if not path.is_file():return
    if path.stat().st_size>64*1024**2:raise ValueError('Native input exceeds bounded diagnostic limit')
    data=path.read_bytes();before=bytes.fromhex(old);after=bytes.fromhex(new)
    if before in data:return
    directory=workspace/'out/beyoud-logs/native-inputs';directory.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(data).hexdigest();destination=directory/(digest+path.suffix)
    if not destination.exists():shutil.copyfile(path,destination)
    report=dict(path=str(path.relative_to(workspace)),sha256=digest,size=len(data),old=old,new=new,
                old_matches=data.count(before),new_matches=data.count(after),status='input-only-native-fix-unvalidated')
    (directory/(digest+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print('Native input preserved privately for offline analysis: '+digest,flush=True)


if __name__=='__main__':
    try:capture(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],sys.argv[4])
    except (OSError,ValueError) as exc:print(f'Native input capture blocked: {exc}',file=sys.stderr);sys.exit(1)
