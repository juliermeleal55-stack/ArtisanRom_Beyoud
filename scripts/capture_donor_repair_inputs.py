#!/usr/bin/env python3
"""Keep selected donor inputs privately so further patch repairs need no firmware re-download."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integration.samloader.metadata import configured_firmwares, get
from integration.native_analysis import analyze

NAMES=('libstagefright.so','framework.jar','services.jar','knoxsdk.jar','SecSettings.apk','SecSettingsIntelligence.apk','StorageManager.apk','SystemUI.apk')
BUDGET=512*1024**2


def capture(workspace,destination):
    descriptor=configured_firmwares(workspace/'out/config.sh','source')[0]
    model,csc,*_=descriptor.split('/')
    root=workspace/'out/fw'/f'{model}_{csc}'
    record=get(workspace/'out/firmware-lock.json',model,csc)
    if (root/'.extracted').read_text().strip()!=record['version']:raise ValueError('Donor extraction does not match firmware lock')
    if destination.exists():raise ValueError('Input destination must be new')
    destination.mkdir(parents=True)
    files=[];used=0
    for name in NAMES:
        candidates=[p for p in root.rglob(name) if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve())]
        if name=='libstagefright.so':candidates=[p for p in candidates if '/lib64/' in str(p)]
        if len(candidates)!=1:
            if name=='libstagefright.so':raise ValueError('Expected one actual donor 64-bit libstagefright')
            files.append(dict(name=name,status='unavailable',reason='missing/ambiguous donor path'));continue
        path=candidates[0];size=path.stat().st_size
        if used+size>BUDGET:
            files.append(dict(name=name,status='unavailable',reason='bounded diagnostic budget'));continue
        target=destination/name;shutil.copyfile(path,target)
        used+=size
        if name=='libstagefright.so':
            report=analyze(target)
            (destination/'libstagefright-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
        files.append(dict(name=name,path=str(path.relative_to(root)),size=size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),status='captured'))
    manifest=dict(schema_version=1,status='private-repair-inputs-not-a-ROM',model=model,csc=csc,version=record['version'],total_bytes=used,files=files)
    (destination/'repair-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('workspace',type=Path);parser.add_argument('destination',type=Path);args=parser.parse_args()
    try:capture(args.workspace,args.destination)
    except (OSError,ValueError,KeyError) as exc:print(f'Donor input capture blocked: {exc}',file=sys.stderr);sys.exit(1)
