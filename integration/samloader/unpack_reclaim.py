#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract a disposable ZIP while reclaiming compressed data already read (Linux only).

zipfile still validates each member's CRC. Once punching starts the source ZIP is
not reusable; on failure no download marker may be written and it must be downloaded again.
"""
import argparse
import ctypes
import errno
import os
from pathlib import Path
import shutil
import stat
import sys
import zipfile

BLOCK = 4096
RESERVE = 2 * 1024**3


def punch(fd, start, end):
    start = (start + BLOCK - 1) // BLOCK * BLOCK
    end = end // BLOCK * BLOCK
    if end <= start:
        return start
    libc = ctypes.CDLL(None, use_errno=True)
    operation = libc.fallocate
    operation.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_longlong, ctypes.c_longlong]
    operation.restype = ctypes.c_int
    if operation(fd, 0x01 | 0x02, start, end - start) != 0:  # KEEP_SIZE | PUNCH_HOLE
        code = ctypes.get_errno()
        raise OSError(code, 'Filesystem cannot reclaim consumed ZIP data; no unsafe full-copy fallback')
    return end


def output_path(destination, info):
    relative = Path(info.filename)
    output = destination / relative
    if (not info.filename or relative == Path('.') or relative.is_absolute()
            or '..' in relative.parts or relative.name.endswith('.beyoud-partial')
            or relative.name == '.beyoud-punch-probe'
            or not output.resolve().is_relative_to(destination.resolve())):
        raise ValueError('Unsafe ZIP path')
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise ValueError('ZIP symlinks are not supported')
    return output


def unpack(source, destination, reserve=RESERVE):
    source = source.resolve()
    destination = destination.resolve()
    if not destination.is_dir():
        raise ValueError('Destination must already exist')
    if not source.is_file():
        raise ValueError('Source ZIP must be a regular file')
    # Hole punching only frees space for extraction when source and destination
    # share a filesystem. Reject cross-device layouts before modifying either.
    if source.stat().st_dev != destination.stat().st_dev:
        raise ValueError('Source ZIP and extraction destination must be on the same filesystem')
    # Fail BEFORE extracting if hole punching is unsupported; test on a disposable sibling.
    with open(destination / '.beyoud-punch-probe', 'xb+') as probe:
        try:
            probe.write(b'x' * (BLOCK * 3))
            probe.flush()
            punch(probe.fileno(), 0, BLOCK * 2)
        finally:
            (destination / '.beyoud-punch-probe').unlink(missing_ok=True)
    with source.open('r+b', buffering=0) as raw, zipfile.ZipFile(raw) as archive:
        infos = archive.infolist()  # Read central directory BEFORE changing the archive.
        seen = set()
        for info in infos:
            output = output_path(destination, info)
            if output == source or output in seen:
                raise ValueError('Duplicate ZIP entry or entry overwrites source')
            if info.is_dir():
                if output.is_symlink() or (output.exists() and not output.is_dir()):
                    raise ValueError(f'ZIP directory conflicts with existing path: {output}')
            elif output.exists() or output.is_symlink():
                raise ValueError(f'Refusing to overwrite existing extraction output: {output}')
            seen.add(output)
        if not infos:
            raise ValueError('Empty firmware ZIP')
        free = shutil.disk_usage(destination).free
        # Conservative lower bound: a final expanded package still needs to fit.
        expanded = sum(i.file_size for i in infos)
        reclaimable = sum(max(0, i.compress_size - 2 * BLOCK) for i in infos)
        if free + reclaimable < expanded + reserve:
            raise ValueError('Insufficient space even after reclaiming the compressed ZIP')
        for info in infos:
            output = output_path(destination, info)
            if info.is_dir():
                output.mkdir(parents=True, exist_ok=True)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            partial = output.with_name(output.name + '.beyoud-partial')
            if partial.exists() or partial.is_symlink():
                raise ValueError(f'Previous partial extraction exists: {partial}')
            try:
                with archive.open(info) as member, partial.open('xb') as target:
                    # Single-reader access: raw.tell() tracks compressed bytes already copied
                    # into ZipExtFile's buffers. No private zipfile attributes or backward seeks.
                    consumed = raw.tell()
                    end = consumed + info.compress_size
                    while True:
                        chunk = member.read(8 * 1024**2)
                        if not chunk:
                            break  # zipfile has checked this member's CRC.
                        if shutil.disk_usage(destination).free < reserve + len(chunk):
                            raise OSError(errno.ENOSPC, 'Extraction reserve reached; aborting without a success marker')
                        target.write(chunk)
                        target.flush()
                        consumed = punch(raw.fileno(), consumed, min(raw.tell(), end))
                os.replace(partial, output)
            except BaseException:
                partial.unlink(missing_ok=True)
                raise
    source.unlink()  # Only after all members passed CRC and all outputs were committed.


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        unpack(args.source, args.destination)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f'ZIP extraction failed: {exc}. Discard this disposable ZIP before retrying.', file=sys.stderr)
        sys.exit(1)
