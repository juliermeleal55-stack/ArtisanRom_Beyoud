#!/usr/bin/env python3
"""Preserve donor auxiliary trees inside system on static targets lacking them.

No partition capacities are invented and no auxiliary payload is discarded.
This is a packaging/layout adaptation, not a claim of boot compatibility.
"""
import json
from pathlib import Path
import shutil
from integration.package_inputs import capture, atomic_json

PARTITIONS = {'system','vendor','product','system_ext','odm','prism','optics',
              'vendor_dlkm','odm_dlkm','system_dlkm'}
EMBED = {'optics','prism','odm'}


def remap(text, old, new):
    result=[]
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            result.append(line);continue
        first=line.split()[0]
        suffix=first[len(old):] if first.startswith(old) else None
        if suffix is None or (suffix and not suffix.startswith(('/', '('))):
            raise ValueError(f'Unexpected metadata path: {first}')
        result.append(new+line[len(old):])
    return '\n'.join(result)+'\n'


def normalize(workspace, codename):
    data=capture(workspace)
    if data['codename']!=codename:raise ValueError('Static layout target mismatch')
    caps=data['stock_image_size_caps']
    work=workspace/'out/target'/codename/'work_dir'
    system=work/'system';inside=system/'system';configs=work/'configs'
    if any(p.is_symlink() or not p.is_dir() for p in (work,system,inside,configs)):
        raise ValueError('Unsafe or missing static system layout')
    trees={p.name for p in work.iterdir() if p.name in PARTITIONS and p.is_dir() and not p.is_symlink()}
    extra=trees-caps.keys()
    if extra-EMBED:
        raise ValueError(f'Unsupported target partition trees: {sorted(extra-EMBED)}')
    plans=[]
    # Check every relocation and its metadata before making any change.
    for name in sorted(extra):
        source=work/name;dest=inside/name;link=system/name
        if dest.exists() or dest.is_symlink():raise ValueError(f'Embedded destination already exists: {dest}')
        if link.is_symlink() or (link.exists() and (not link.is_dir() or any(link.iterdir()))):
            raise ValueError(f'Root mountpoint collision: {link}')
        changes={}
        for prefix,old,new in [('fs_config',name,'system/'+name),('file_context','/'+name,'/system/'+name)]:
            original=configs/(prefix+'-'+name);target=configs/(prefix+'-system')
            if original.is_symlink() or target.is_symlink() or not original.is_file() or not target.is_file():
                raise ValueError(f'Missing/unsafe metadata for {name}')
            if not original.read_text().strip():raise ValueError(f'Empty metadata for {name}')
            changes[prefix]=remap(original.read_text(),old,new)
        plans.append((name,source,dest,link,changes))
    report={'schema_version':1,'status':'layout-only-not-boot-validated','embedded':[],'fstab_edits':[]}
    for name,source,dest,link,changes in plans:
        shutil.move(str(source),str(dest))
        if link.exists():link.rmdir()  # Only an empty mountpoint, checked above.
        link.symlink_to('/system/'+name)
        for prefix in ('fs_config','file_context'):
            target=configs/(prefix+'-system')
            rootkey=name if prefix=='fs_config' else '/'+name
            lines=[l for l in target.read_text().splitlines() if not l.split() or l.split()[0]!=rootkey]
            entry=f'{name} 0 0 777' if prefix=='fs_config' else f'/{name} u:object_r:system_file:s0'
            target.write_text('\n'.join(lines)+'\n'+changes[prefix]+entry+'\n')
        report['embedded'].append({'partition':name,'destination':'system/system/'+name,'root_link':'/system/'+name})
    moved={item['partition'] for item in report['embedded']}
    for path in sorted(work.rglob('fstab*')):
        if path.is_symlink() or not path.is_file():continue
        lines=path.read_text().splitlines(keepends=True);kept=[];removed=0
        for line in lines:
            parts=line.split()
            if not line.lstrip().startswith('#') and len(parts)>=2 and parts[1] in {'/'+name for name in moved}:
                removed+=1
            else:kept.append(line)
        if removed:
            path.write_text(''.join(kept))
            report['fstab_edits'].append({'path':str(path.relative_to(work)),'removed_mount_entries':removed})
    # A hard lower bound, not an estimate of ext4 overhead or physical PIT size.
    # Catch payloads that cannot fit before retiring firmware/building images.
    report['payload_bytes']={}
    for name in sorted(trees-extra):
        seen=set();size=0
        for path in (work/name).rglob('*'):
            if path.is_symlink() or not path.is_file():continue
            stat=path.stat();key=(stat.st_dev,stat.st_ino)
            if key not in seen:size+=stat.st_size;seen.add(key)
        report['payload_bytes'][name]=size
        if size>caps[name]:raise ValueError(f'{name} payload lower bound {size} exceeds stock image cap {caps[name]}')
    atomic_json(workspace/'out/beyoud-logs/static-layout.json',report)
    print(json.dumps(report,indent=2),flush=True)
    return report
