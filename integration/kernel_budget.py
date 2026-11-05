#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Change only the pinned kernel driver's CPU count in a disposable script copy."""
from pathlib import Path
import sys

TOOLCHAIN_URL = 'https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/refs/heads/main/clang-r547379.tar.gz'

ANCHOR = 'CORES=`cat /proc/cpuinfo | grep -c processor`'


def bounded(text):
    if text.count(ANCHOR) != 1:
        raise ValueError('Unexpected pinned kernel CPU selection')
    return text.replace(ANCHOR, 'CORES=${BEYOUD_JOBS:-1}\n[[ "$CORES" =~ ^[1-4]$ ]] || exit 64')


def harden_download(text):
    curl = 'curl -LJOk ' + TOOLCHAIN_URL
    tar = 'tar xf main-clang-r547379.tar.gz'
    if text.count(curl) != 1 or text.count(tar) != 1:
        raise ValueError('Unexpected pinned kernel toolchain download')
    text = text.replace(curl, 'curl --fail --location --retry 2 --output main-clang-r547379.tar.gz ' + TOOLCHAIN_URL + ' || exit 1')
    return text.replace(tar, tar + ' || exit 1')


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(harden_download(bounded(Path(sys.argv[1]).read_text())))
