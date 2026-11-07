#!/usr/bin/env python3
"""Preserve auxiliary payloads in a static system image, without following aliases.

Layout adaptation only: neither this module nor its report certifies boot.
"""
import filecmp
import json
import re
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
        # Artisan's extractor removes the mount path from the root stat row:
        # ' / 0 0 755' becomes ' 0 0 755 capabilities=0x0', not '<part> ...'.
        if not old.startswith('/') and re.fullmatch(r'\s*[0-9]+\s+[0-9]+\s+[0-7]{3,4}(?:\s+capabilities=0x[0-9a-fA-F]+)?\s*',line):
            result.append(new+' '+line.strip());continue
        first=line.split()[0]
        if not matches(first,old):raise ValueError(f'Unexpected metadata path: {first}')
        result.append(line.replace(old,new,1))
    return '\n'.join(result)+'\n'


def check_merge(source, destination, aliases=frozenset()):
    """Reject differing nodes BEFORE moving any payload; never follow symlinks."""
    if source in aliases or destination in aliases:return
    if not exists(destination):return
    if source.is_symlink() or destination.is_symlink():
        if source.is_symlink() and destination.is_symlink() and source.readlink()==destination.readlink():return
    elif source.is_dir() and destination.is_dir():
        for item in source.iterdir():check_merge(item,destination/item.name,aliases)
        return
    elif source.is_file() and destination.is_file() and filecmp.cmp(source,destination,shallow=False):
        return
    details=lambda p: ('symlink -> '+str(p.readlink())) if p.is_symlink() else ('directory' if p.is_dir() else 'file')
    raise ValueError(f'Conflicting auxiliary payload: {source} ({details(source)}) -> {destination} ({details(destination)})')


def merge(source, destination, aliases=frozenset()):
    # check_merge has already validated all source nodes and metadata.
    if not exists(destination):
        shutil.move(str(source),str(destination));return
    if source in aliases:
        source.unlink();return
    if source.is_dir() and not source.is_symlink():
        for item in list(source.iterdir()):merge(item,destination/item.name,aliases)
        source.rmdir()
    else:
        source.unlink()  # Exact duplicate data/link, not a conflicting file.


def equivalent_metadata(left, right):
    if left==right:return True
    if not left or not right or left[0]!=right[0] or left[0].startswith('/'):
        return False
    def fields(parts):
        if len(parts) not in (4,5) or not all(p.isdecimal() for p in parts[1:3]) or not re.fullmatch(r'[0-7]{3,4}',parts[3]):return None
        cap=0
        if len(parts)==5:
            match=re.fullmatch(r'capabilities=0x([0-9a-fA-F]+)',parts[4])
            if not match:return None
            cap=int(match.group(1),16)
        return int(parts[1]),int(parts[2]),int(parts[3],8),cap
    a,b=fields(left),fields(right)
    return a is not None and a==b


def metadata(current, incoming):
    lines=current.splitlines()
    for line in incoming.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        parts=line.split();key=parts[0]
        previous=[l.split() for l in lines if l.strip() and not l.lstrip().startswith('#') and l.split()[0]==key]
        if any(not equivalent_metadata(old,parts) for old in previous):raise ValueError(f'Conflicting auxiliary metadata: {key}')
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
        aliases=set();self_aliases=set()
        if not link.is_symlink() and link.is_dir():
            for child in link.rglob('*'):
                if not child.is_symlink():continue
                relative=child.relative_to(link).as_posix()
                permitted={f'/{base}/{name}/{relative}' for base in ('vendor','system/vendor','mnt/vendor')}
                if str(child.readlink()) in permitted:aliases.add(child)
                elif str(child.readlink())==f'/{name}/{relative}':
                    aliases.add(child);self_aliases.add(child)
            check_merge(source,link,aliases)
            if exists(dest):check_merge(link,dest,aliases)
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
                        replaced=False
                        for child in aliases:
                            relative=child.relative_to(link)
                            if (child in self_aliases or exists(source/relative) or exists(dest/relative)) and matches(parts[0],old+'/'+relative.as_posix()):
                                replaced=True;break
                        if not replaced:legacy.append(line.replace(old,new,1))
                else:keep.append(line)
            current='\n'.join(keep)+'\n'
            current=metadata(current,'\n'.join(legacy))
            current=metadata(current,remap(original.read_text(),old,new))
            entry=f'{name} 0 0 777' if prefix=='fs_config' else f'/{name} u:object_r:system_file:s0'
            texts[prefix]=metadata(current,entry)
        plans.append((name,source,dest,link,alias,aliases,self_aliases))
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
    for name,source,dest,link,alias,aliases,self_aliases in plans:
        report['embedded'].append({'partition':name,'destination':'system/system/'+name,
                                   'root_link':'/system/'+name,'previous_root_link':alias,
                                   'legacy_aliases':[{'path':str(p.relative_to(system)),'target':str(p.readlink()),'self_forwarder':p in self_aliases} for p in sorted(aliases)]})
        if not check_only:
            merge(source,dest)
            # These routing links would point back to themselves after embedding.
            # Their target data comes from source; no target directory is removed.
            for child in self_aliases:child.unlink()
            if link.is_symlink():link.unlink()  # Do not remove or traverse its target.
            elif link.exists():merge(link,dest,aliases)
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
