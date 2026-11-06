#!/usr/bin/env python3
"""Preserve auxiliary payloads in a static system image, without following aliases.

Layout adaptation only: neither this module nor its report certifies boot.
"""
import filecmp
import json
from pathlib import Path
import shutil
from integration.package_inputs import capture, atomic_json

PARTITIONS = {'system','vendor','product','system_ext','odm','prism','optics',
              'vendor_dlkm','odm_dlkm','system_dlkm'}
EMBED = {'optics','prism','odm'}


def exists(path):
    return path.is_symlink() or path.exists()


def matches(value, prefix):
    return value == prefix or value.startswith((prefix+'/',prefix+'('))


def remap(text, old, new):
    result=[]
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            result.append(line);continue
        first=line.split()[0]
        if not matches(first,old):raise ValueError(f'Unexpected metadata path: {first}')
        result.append(line.replace(old,new,1))
    return '\n'.join(result)+'\n'


def check_merge(source, destination):
    """Reject differing nodes BEFORE moving any payload; never follow symlinks."""
    if not exists(destination):return
    if source.is_symlink() or destination.is_symlink():
        if source.is_symlink() and destination.is_symlink() and source.readlink()==destination.readlink():return
    elif source.is_dir() and destination.is_dir():
        for item in source.iterdir():check_merge(item,destination/item.name)
        return
    elif source.is_file() and destination.is_file() and filecmp.cmp(source,destination,shallow=False):
        return
    raise ValueError(f'Conflicting auxiliary payload: {source} -> {destination}')


def merge(source, destination):
    # check_merge has already validated all source nodes and metadata.
    if not exists(destination):
        shutil.move(str(source),str(destination));return
    if source.is_dir() and not source.is_symlink():
        for item in list(source.iterdir()):merge(item,destination/item.name)
        source.rmdir()
    else:
        source.unlink()  # Exact duplicate data/link, not a conflicting file.


def metadata(current, incoming):
    lines=current.splitlines()
    for line in incoming.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        parts=line.split();key=parts[0]
        previous=[l.split() for l in lines if l.strip() and not l.lstrip().startswith('#') and l.split()[0]==key]
        if any(old!=parts for old in previous):raise ValueError(f'Conflicting auxiliary metadata: {key}')
        if not previous:lines.append(line)
    return '\n'.join(lines)+'\n'


def normalize(workspace, codename, check_only=False):
    data=capture(workspace)
    if data['codename']!=codename:raise ValueError('Static layout target mismatch')
    caps=data['stock_image_size_caps']
    work=workspace/'out/target'/codename/'work_dir'
    system=work/'system';inside=system/'system';configs=work/'configs'
    if any(p.is_symlink() or not p.is_dir() for p in (work,system,inside,configs)):
        raise ValueError('Unsafe or missing static system layout')
    trees={p.name for p in work.iterdir() if p.name in PARTITIONS and not p.is_symlink() and p.is_dir()}
    extra=trees-caps.keys()
    if extra-EMBED:raise ValueError(f'Unsupported target partition trees: {sorted(extra-EMBED)}')
    plans=[];texts={}
    for prefix in ('fs_config','file_context'):
        path=configs/(prefix+'-system')
        if path.is_symlink() or not path.is_file():raise ValueError('Missing/unsafe system metadata')
        texts[prefix]=path.read_text()
    # All aliases, payload collisions and metadata are checked before mutations.
    for name in sorted(extra):
        source=work/name;dest=inside/name;link=system/name
        if exists(dest) and (dest.is_symlink() or not dest.is_dir()):raise ValueError(f'Unsafe embedded destination: {dest}')
        alias=None
        if link.is_symlink():
            alias=str(link.readlink())
            allowed={f'/{base}/{name}' for base in ('system','vendor','system/vendor','mnt/vendor')}
            allowed |= {value.lstrip('/') for value in allowed}
            if alias not in allowed:raise ValueError(f'Unexpected root alias: {link} -> {alias}')
        elif exists(link) and not link.is_dir():raise ValueError(f'Root mountpoint collision: {link}')
        if not link.is_symlink() and link.is_dir():
            check_merge(source,link)
            if exists(dest):check_merge(link,dest)
        check_merge(source,dest)
        for prefix,old,new in [('fs_config',name,'system/'+name),('file_context','/'+name,'/system/'+name)]:
            original=configs/(prefix+'-'+name)
            if original.is_symlink() or not original.is_file() or not original.read_text().strip():
                raise ValueError(f'Missing/unsafe metadata for {name}')
            keep=[];legacy=[]
            for line in texts[prefix].splitlines():
                parts=line.split()
                if parts and not line.lstrip().startswith('#') and matches(parts[0],old):
                    # Root row describes the old mountpoint/link, not new payload.
                    if parts[0]!=old and not link.is_symlink() and link.is_dir():
                        legacy.append(line.replace(old,new,1))
                else:keep.append(line)
            current='\n'.join(keep)+'\n'
            current=metadata(current,'\n'.join(legacy))
            current=metadata(current,remap(original.read_text(),old,new))
            entry=f'{name} 0 0 777' if prefix=='fs_config' else f'/{name} u:object_r:system_file:s0'
            texts[prefix]=metadata(current,entry)
        plans.append((name,source,dest,link,alias))
    report={'schema_version':1,'status':'layout-only-not-boot-validated',
            'check_only':check_only,'embedded':[],'fstab_edits':[],'payload_bytes':{}}
    # Count a conservative payload lower bound before deleting firmware. Aliases
    # are never followed; duplicate hardlinks are counted only once per image.
    for name in sorted(trees-extra):
        roots=[work/name]
        if name=='system':
            roots += [p[1] for p in plans]
        seen=set();projected=set();size=0
        for root in roots:
            for path in root.rglob('*'):
                if path.is_symlink() or not path.is_file():continue
                relative=path.relative_to(root)
                if name=='system':
                    if root!=work/name:relative=Path('system')/root.name/relative
                    elif relative.parts[0] in extra:relative=Path('system')/relative
                if relative in projected:continue
                projected.add(relative)
                stat=path.stat();key=(stat.st_dev,stat.st_ino)
                if key not in seen:size+=stat.st_size;seen.add(key)
        report['payload_bytes'][name]=size
        if size>caps[name]:raise ValueError(f'{name} payload lower bound {size} exceeds stock image cap {caps[name]}')
    for name,source,dest,link,alias in plans:
        report['embedded'].append({'partition':name,'destination':'system/system/'+name,
                                   'root_link':'/system/'+name,'previous_root_link':alias})
        if not check_only:
            merge(source,dest)
            if link.is_symlink():link.unlink()  # Do not remove or traverse its target.
            elif link.exists():merge(link,dest)
            link.symlink_to('/system/'+name)
    moved={item['partition'] for item in report['embedded']}
    fstab_changes=[]
    for path in sorted(work.rglob('fstab*')):
        if path.is_symlink() or not path.is_file():continue
        lines=path.read_text().splitlines(keepends=True);kept=[];removed=0
        for line in lines:
            parts=line.split()
            if not line.lstrip().startswith('#') and len(parts)>=2 and parts[1] in {'/'+name for name in moved}:removed+=1
            else:kept.append(line)
        if removed:
            fstab_changes.append((path,''.join(kept)))
            report['fstab_edits'].append({'path':str(path.relative_to(work)),'removed_mount_entries':removed})
    if not check_only:
        for prefix,text in texts.items():(configs/(prefix+'-system')).write_text(text)
        for path,text in fstab_changes:path.write_text(text)
    log='static-layout-plan.json' if check_only else 'static-layout.json'
    atomic_json(workspace/'out/beyoud-logs'/log,report)
    print(json.dumps(report,indent=2),flush=True)
    return report
