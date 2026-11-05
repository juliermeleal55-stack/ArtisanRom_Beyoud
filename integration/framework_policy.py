# SPDX-License-Identifier: GPL-3.0-or-later
"""Replace only the brittle pinned Freecess hunk with a guarded semantic edit."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = Path('unica/patches/miscs/smali/system/framework/services.jar/0001-Better-model-detection-in-FreecessController.patch')
CUSTOMIZE = Path('unica/patches/miscs/customize.sh')


def install(workspace):
    original_patch = (ROOT / 'reference/build' / PATCH).read_bytes()
    original_script = (ROOT / 'reference/build' / CUSTOMIZE).read_bytes()
    if (workspace / PATCH).read_bytes() != original_patch or (workspace / CUSTOMIZE).read_bytes() != original_script:
        raise ValueError('Unexpected pinned Freecess module; manual review required')
    addition = '''
# Beyoud: retain the model-detection fix without compiler-specific v2/jumbo context.
DECODE_APK "system" "system/framework/services.jar" || exit 1
python3 "$SRC_DIR/integration/freecess.py" "$APKTOOL_DIR/system/framework/services.jar" || exit 1
'''
    (workspace / CUSTOMIZE).write_bytes(original_script + addition.encode())
    # Removed ONLY after the replacement was installed. This is not a skipped fix.
    (workspace / PATCH).unlink()
