# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit Exynos candidates; never infer support for other Galaxy variants."""
TARGETS = {
    'beyond2lte': {'model': 'SM-G975F', 'legacy_model': 'SM-G975N', 'name': 'Galaxy S10+'},
    'beyond1lte': {'model': 'SM-G973F', 'legacy_model': 'SM-G973N', 'name': 'Galaxy S10'},
}


def select(codename):
    if codename not in TARGETS:
        raise ValueError(f'Unsupported target: {codename}')
    return TARGETS[codename]


def from_marker(marker):
    codename = marker.get('codename')
    if codename is None:
        matches = [key for key, value in TARGETS.items() if value['model'] == marker.get('target')]
        if len(matches) != 1:
            raise ValueError('Unknown workspace model')
        codename = matches[0]
    target = select(codename)
    if target['model'] != marker.get('target'):
        raise ValueError('Workspace model/codename mismatch')
    return codename, target
