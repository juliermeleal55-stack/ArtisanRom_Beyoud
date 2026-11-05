#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Change only the pinned kernel driver's CPU count in a disposable script copy."""
from pathlib import Path
import sys

ANCHOR = 'CORES=`cat /proc/cpuinfo | grep -c processor`'


def bounded(text):
    if text.count(ANCHOR) != 1:
        raise ValueError('Unexpected pinned kernel CPU selection')
    return text.replace(ANCHOR, 'CORES=${BEYOUD_JOBS:-1}\n[[ "$CORES" =~ ^[1-4]$ ]] || exit 64')


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(bounded(Path(sys.argv[1]).read_text()))
