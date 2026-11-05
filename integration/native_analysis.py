#!/usr/bin/env python3
"""Read-only ELF/AArch64 diagnostics. Candidate sites NEVER authorize a patch."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

LIMIT = 64 * 1024**2
LEGACY = {
    'video_svc': 'da4a0594e0031a2a22feff17',
    'hdr10_plus': '010140f90a4d0594604d0034',
}


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def branch(word, pc):
    if word & 0x7c000000 == 0x14000000:
        return {'kind': 'BL' if word & 0x80000000 else 'B',
                'target': pc + (signed(word & 0x3ffffff, 26) << 2)}
    if word & 0x7e000000 == 0x34000000:
        return {'kind': 'CBNZ' if word & 0x01000000 else 'CBZ',
                'target': pc + (signed((word >> 5) & 0x7ffff, 19) << 2)}
    return None


def executable_segments(data):
    if len(data) < 64 or data[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('Expected ELF64 little-endian version 1')
    kind, machine, version = struct.unpack_from('<HHI', data, 16)
    if kind != 3 or machine != 183 or version != 1:
        raise ValueError('Expected an AArch64 shared library')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    ehsize, entsize, count = struct.unpack_from('<HHH', data, 52)
    if ehsize != 64 or entsize != 56 or not 0 < count <= 1024 or phoff < 64 or phoff + count * entsize > len(data):
        raise ValueError('Invalid ELF program-header table')
    result = []
    for i in range(count):
        ptype, flags, offset, address, _, size, memsize, _ = struct.unpack_from('<IIQQQQQQ', data, phoff + i * entsize)
        if ptype != 1:
            continue
        if size > memsize or offset + size > len(data):
            raise ValueError('Truncated ELF load segment')
        if flags & 1 and size:
            if offset % 4 or address % 4:
                raise ValueError('Misaligned executable segment')
            result.append((offset, address, size))
    if not result:
        raise ValueError('No executable load segment')
    for i, (offset, address, size) in enumerate(result):
        for other, virtual, length in result[:i]:
            if (max(offset, other) < min(offset + size, other + length)
                    or max(address, virtual) < min(address + size, virtual + length)):
                raise ValueError('Overlapping executable segments')
    return result


def analyze(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > LIMIT:
        raise ValueError('Expected a regular native input no larger than 64 MiB')
    data = path.read_bytes()
    segments = executable_segments(data)
    patterns = {name: bytes.fromhex(value) for name, value in LEGACY.items()}
    exact = {name: [] for name in LEGACY}
    counts = {name: 0 for name in LEGACY}
    candidates = []
    total = 0
    for offset, address, size in segments:
        def site(position):
            instructions = []
            for at in range(max(offset, position - 16), min(offset + size - 3, position + 28), 4):
                pc = address + at - offset
                word = struct.unpack_from('<I', data, at)[0]
                item = {'offset': at, 'address': pc, 'word': f'{word:08x}'}
                decoded = branch(word, pc)
                if decoded:
                    decoded['target_executable'] = any(base <= decoded['target'] < base + length for _, base, length in segments)
                    item.update(decoded)
                instructions.append(item)
            return {'offset': position, 'address': address + position - offset, 'instructions': instructions}
        for position in range(offset, offset + size - 11, 4):
            chunk = data[position:position + 12]
            for name, pattern in patterns.items():
                if chunk == pattern:
                    counts[name] += 1
                    if len(exact[name]) < 128:
                        exact[name].append(site(position))
            first, middle, last = struct.unpack('<III', chunk)
            # Stable anchors aid human inspection ONLY. Registers/branches are
            # deliberately not wildcard replacements and no bytes are written.
            svc = first & 0xfc000000 == 0x94000000 and middle == 0x2a1a03e0 and last & 0xfc000000 == 0x14000000
            hdr = first == 0xf9400101 and middle & 0xfc000000 == 0x94000000 and last & 0x7e000000 == 0x34000000
            if svc or hdr:
                total += 1
                if len(candidates) < 128:
                    candidates.append(dict(anchor='video_svc' if svc else 'hdr10_plus', **site(position)))
    return {'schema_version': 1, 'status': 'analysis-only-no-patch-approved',
            'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
            'executable_segments': [{'offset': o, 'address': a, 'size': s} for o, a, s in segments],
            'legacy_exact_sites': exact, 'legacy_exact_counts': counts,
            'legacy_sites_truncated': any(counts[name] > len(exact[name]) for name in exact),
            'candidate_count': total,
            'candidates_truncated': total > len(candidates), 'inspection_candidates': candidates}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.input), indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Native analysis blocked: {exc}\n')
