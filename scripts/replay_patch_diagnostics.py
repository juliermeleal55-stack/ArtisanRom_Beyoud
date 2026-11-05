#!/usr/bin/env python3
"""Test current adaptations against PRIVATE prior donor snapshots, without firmware downloads."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
from smali_patch import apply

ROOT=Path(__file__).resolve().parents[1]


def replay(artifacts):
    reports=list(artifacts.rglob('patch-preflight.json'))
    if len(reports)!=1:raise ValueError('Expected exactly one previous preflight report')
    report=json.loads(reports[0].read_text())
    specs=json.loads((ROOT/'integration/semantic_smali.json').read_text())
    sources={hashlib.sha256(p.read_bytes()).hexdigest():p for p in artifacts.rglob('*.smali') if p.is_file() and not p.is_symlink()}
    results=[]
    for event in report['events']:
        name=event.get('patch')
        if name not in specs:continue
        inputs=event.get('inputs',{})
        item=dict(patch=name)
        if not inputs or any(digest not in sources for digest in inputs.values()):
            item.update(status='unavailable',reason='Exact input snapshot not retained; not treated as passing')
            results.append(item);continue
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp);prefixes=set()
            for path,digest in inputs.items():
                relative=Path(path)
                if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe replay input path')
                index=next(i for i,p in enumerate(relative.parts) if re.fullmatch(r'smali(?:_classes\d+)?',p))
                prefixes.add(Path(*relative.parts[:index]))
                output=workspace/relative;output.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(sources[digest],output)
            if len(prefixes)!=1:raise ValueError('Patch inputs must belong to one decoded APK')
            patch=workspace/name;patch.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/'reference/build'/name,patch)
            result,_=apply(workspace,workspace/next(iter(prefixes)),patch)
            item.update(status='passed' if not result.returncode else 'failed',detail=result.stderr[-1200:])
            results.append(item)
    print(json.dumps(dict(scope='Only exact retained input snapshots; not whole-ROM validation',results=results),indent=2))
    if any(e['status']=='failed' for e in results):raise ValueError('A retained real-donor input rejected its adaptation')
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('artifacts',type=Path);args=parser.parse_args()
    try:replay(args.artifacts)
    except (OSError,ValueError) as exc:print(str(exc),file=sys.stderr);sys.exit(1)
