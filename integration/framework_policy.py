# SPDX-License-Identifier: GPL-3.0-or-later
"""Replace only the brittle pinned Freecess hunk with a guarded semantic edit."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = Path('unica/patches/miscs/smali/system/framework/services.jar/0001-Better-model-detection-in-FreecessController.patch')
CORE_PATCH = Path('unica/patches/miscs/smali/system/framework/framework.jar/0001-Better-device-model-detection-in-CoreRune.patch')
SETTINGS_SCRIPT = Path('unica/mods/settings/customize.sh')
SETTINGS_PATCH = Path('unica/mods/settings/smali/system/priv-app/SecSettings/SecSettings.apk/0003-Show-real-device-model-number.patch')
APKTOOL = Path('scripts/apktool.sh')
CUSTOMIZE = Path('unica/patches/miscs/customize.sh')


def install(workspace):
    original_patch = (ROOT / 'reference/build' / PATCH).read_bytes()
    original_script = (ROOT / 'reference/build' / CUSTOMIZE).read_bytes()
    if (workspace / PATCH).read_bytes() != original_patch or (workspace / CUSTOMIZE).read_bytes() != original_script:
        raise ValueError('Unexpected pinned Freecess module; manual review required')
    for relative in (CORE_PATCH, APKTOOL, SETTINGS_SCRIPT, SETTINGS_PATCH):
        if (workspace / relative).read_bytes() != (ROOT / 'reference/build' / relative).read_bytes():
            raise ValueError('Unexpected pinned CoreRune/apktool input')
    apktool = (workspace / APKTOOL).read_text()
    old = 'unzip -q \"$INPUT_FILE\" \"res/*\" -d \"$OUTPUT_PATH/unknown\"'
    if apktool.count(old) != 1:
        raise ValueError('Unexpected framework resource extraction')
    apktool = apktool.replace(old, 'unzip -oq \"$INPUT_FILE\" \"res/*\" -d \"$OUTPUT_PATH/unknown\" || return 1')
    addition = '''
# Beyoud: retain the model-detection fix without compiler-specific v2/jumbo context.
DECODE_APK "system" "system/framework/services.jar" || exit 1
python3 "$SRC_DIR/integration/freecess.py" "$APKTOOL_DIR/system/framework/services.jar" || exit 1
DECODE_APK "system" "system/framework/framework.jar" || exit 1
python3 "$SRC_DIR/integration/corerune.py" "$APKTOOL_DIR/system/framework/framework.jar" || exit 1
'''
    (workspace / CUSTOMIZE).write_bytes(original_script + addition.encode())
    # Removed ONLY after the replacement was installed. This is not a skipped fix.
    (workspace / APKTOOL).write_text(apktool)
    (workspace / PATCH).unlink()
    (workspace / CORE_PATCH).unlink()
    settings = (workspace / SETTINGS_SCRIPT).read_text()
    settings += '\nDECODE_APK "system" "system/priv-app/SecSettings/SecSettings.apk" || exit 1\npython3 "$SRC_DIR/integration/settings_model.py" "$APKTOOL_DIR/system/priv-app/SecSettings/SecSettings.apk" || exit 1\n'
    (workspace / SETTINGS_SCRIPT).write_text(settings)
    (workspace / SETTINGS_PATCH).unlink()
