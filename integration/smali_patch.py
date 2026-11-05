#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply legacy hunks strictly, relocating only verified class paths between DEXes."""
from pathlib import Path
import re
import hashlib
import json
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from smali_paths import resolve
from semantic_smali import plan


def normalize(decoded, text):
    targets = []
    mapping = {}
    for target in re.findall(r'(?m)^\+\+\+ b/(.+)$', text):
        path = Path(target)
        if path.is_absolute() or '..' in path.parts or '\\' in target:
            raise ValueError('Unsafe patch target')
        if re.match(r'^smali(?:_classes\d+)?/', target):
            actual = resolve(decoded, target)
        else:
            actual = decoded / path
        if actual.is_symlink() or not actual.resolve().is_relative_to(decoded.resolve()):
            raise ValueError('Unsafe patch destination')
        mapping[target] = actual.relative_to(decoded).as_posix()
        targets.append(actual)
    if not targets or len(set(targets)) != len(targets):
        raise ValueError('Empty or duplicate patch targets')
    lines = []
    for line in text.splitlines(keepends=True):
        # Rewrite headers only. Instructions, registers, labels and hunk context
        # stay byte-for-byte intact; git must still accept the full change.
        if line.startswith(('diff --git ', '--- a/', '+++ b/')):
            for old,new in mapping.items():
                if line.startswith('diff --git '):
                    line=line.replace(' a/'+old+' b/'+old, ' a/'+new+' b/'+new)
                elif line.rstrip('\n') == '--- a/'+old:
                    line='--- a/'+new+'\n'
                elif line.rstrip('\n') == '+++ b/'+old:
                    line='+++ b/'+new+'\n'
        lines.append(line)
    return ''.join(lines), targets, mapping


def apply_text(workspace, decoded, text):
    text,targets,mapping=normalize(decoded,text)
    inputs={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest() for p in targets if p.is_file()}
    command=['git','apply','--directory='+str(decoded),'--unsafe-paths','--verbose']
    checked=subprocess.run(command+['--check','-'],input=text,cwd=workspace,capture_output=True,text=True)
    result=checked if checked.returncode else subprocess.run(command+['-'],input=text,cwd=workspace,capture_output=True,text=True)
    moves='\n'.join(old+' -> '+new for old,new in mapping.items() if old!=new)
    if moves:result.stdout='Verified DEX relocation:\n'+moves+'\n'+result.stdout
    result.input_hashes=inputs
    return result,targets


def apply(workspace, decoded, patch):
    try:
        semantic=plan(workspace,decoded,patch)
        if semantic is not None:
            inputs={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest() for p in semantic}
            for p,text in semantic.items():
                if text!=p.read_text():p.write_text(text)
            result=subprocess.CompletedProcess(['semantic_smali'],0,'Verified pinned semantic equivalent: '+str(patch)+'\n','')
            result.input_hashes=inputs
            return result,list(semantic)
        try:
            result,targets=apply_text(workspace,decoded,patch.read_text())
        except (OSError,ValueError) as exc:
            result,targets=subprocess.CompletedProcess(['smali_patch'],1,'',str(exc)),[]
        if result.returncode:
            registry=json.loads(Path(__file__).with_name('rebased_smali.json').read_text())
            key=str(patch.resolve().relative_to(workspace.resolve()))
            spec=registry.get(key)
            if spec:
                raw=patch.read_bytes()
                digest=lambda b:hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
                if digest(raw)!=spec['legacy_sha']:raise ValueError('Legacy service patch hash changed')
                alternative=Path(__file__).parent/spec['file']
                data=alternative.read_bytes()
                if digest(data)!=spec['sha']:raise ValueError('Rebased service patch hash changed')
                result,targets=apply_text(workspace,decoded,data.decode())
                result.stdout='Strict pinned service rebase: '+key+'\n'+result.stdout
        return result,targets
    except (OSError,ValueError) as exc:
        return subprocess.CompletedProcess(['smali_patch'],1,'',str(exc)),[]


if __name__=='__main__':
    result,_=apply(*(Path(x) for x in sys.argv[1:4]))
    print(result.stdout,end='')
    print(result.stderr,end='',file=sys.stderr)
    sys.exit(result.returncode)
