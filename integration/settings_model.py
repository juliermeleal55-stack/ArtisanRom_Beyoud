#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retain the historical Settings model fix without fixed dex/register context."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from corerune import apply

if __name__ == '__main__':
    try:
        apply(Path(sys.argv[1]), 'ModelNameGetter.smali',
              'Lcom/samsung/android/settings/deviceinfo/aboutphone/ModelNameGetter;',
              [('ro.product.model', 'ro.boot.em.model')])
    except (OSError, ValueError) as exc:
        print(f'Settings model adaptation blocked: {exc}', file=sys.stderr)
        sys.exit(1)
