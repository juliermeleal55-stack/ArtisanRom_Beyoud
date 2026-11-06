# SPDX-License-Identifier: GPL-3.0-or-later
"""Guarded DEX relocation for existing shell recipes, without altering replacements."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def rebase_camera_native_patches(text):
    # S926BXXSIEZJ1 donor: configureSVC failure logs, then bypasses only the
    # error-return path at ACodec::setupVideoEncoder (branch target 0xec8a4).
    old_svc='HEX_PATCH "$WORK_DIR/system/system/lib64/libstagefright.so" "da4a0594e0031a2a22feff17" "da4a0594e0031a2a19000014"'
    new_svc='HEX_PATCH "$WORK_DIR/system/system/lib64/libstagefright.so" "82fbffb042301f91c000805213f30594e0031a2a47feff17" "82fbffb042301f91c000805213f30594e0031a2a0e000014"'
    # The relocated strcasecmp/CBZ pair gates the HDR10+ recording assert.
    old_hdr='HEX_PATCH "$WORK_DIR/system/system/lib64/libstagefright.so" "010140f90a4d0594604d0034" "010140f90a4d05941f2003d5"'
    new_hdr='HEX_PATCH "$WORK_DIR/system/system/lib64/libstagefright.so" "010140f935f5059400470034" "010140f935f505941f2003d5"'
    for old, new, label in ((old_svc,new_svc,'Video SVC'),(old_hdr,new_hdr,'HDR10+')):
        if text.count(old) != 1:
            raise ValueError('Unexpected pinned '+label+' native patch command')
        text=text.replace(old,new,1)
    return text


def install(workspace):
    relative=Path('scripts/utils/smali_utils.sh');path=workspace/relative
    if path.read_bytes()!=(ROOT/'reference/build'/relative).read_bytes():raise ValueError('Unexpected pinned SMALI_PATCH helper')
    text=path.read_text();anchor='    # Check if provided smali exists\n'
    if text.count(anchor)!=1:raise ValueError('Unexpected SMALI_PATCH class lookup')
    text=text.replace(anchor,'    SMALI="$(python3 "$SRC_DIR/integration/smali_paths.py" "$FILE_PATH" "$SMALI")" || return 1\n\n'+anchor)
    path.write_text(text)
    for relative in ('unica/patches/rro/customize.sh','platform/exynos9820/patches/camera/customize.sh'):
        path=workspace/relative
        if path.read_bytes()!=(ROOT/'reference/build'/relative).read_bytes():raise ValueError('Unexpected pinned resource/camera recipe')
    rro=workspace/'unica/patches/rro/customize.sh';text=rro.read_text()
    begin=text.index('sed -i -e "/config_enableRoundedCorner/d"')
    text=text[:begin]+'python3 "$SRC_DIR/integration/overlay_resources.py" "$APKTOOL_DIR/product/overlay/SystemUI__${SYSTEM_NAME}__auto_generated_rro_product.apk" || exit 1\n'
    rro.write_text(text)
    # Preserve every required stock blob import and native check; only serialize
    # workers and treat an already-absent optional deletion as the desired state.
    camera=workspace/'platform/exynos9820/patches/camera/customize.sh';text=camera.read_text()
    text=rebase_camera_native_patches(text)
    old='    DELETE_FROM_WORK_DIR "system" "$blob" &'
    if text.count(old)!=1:raise ValueError('Unexpected camera deletion loop')
    text=text.replace(old,'''    if [[ -e "$WORK_DIR/system/$blob" || -L "$WORK_DIR/system/$blob" ]]; then
        DELETE_FROM_WORK_DIR "system" "$blob" || exit 1
    fi''')
    text=re.sub(r'(?m)^(\s*ADD_TO_WORK_DIR[^\n]+) &$',r'\1 || exit 1',text)
    text=text.replace('wait $(jobs -p) || exit 1',': # Camera operations above are serial and checked.')
    camera.write_text(text)
    # Both literal paths and FTP lists keep their exact package/class suffix.
    # Resolve only the DEX component; absent/ambiguous classes still stop the job.
    pattern=re.compile(r'"\$APKTOOL_DIR/([^"\n]*smali(?:_classes\d+)?/[^"\n]+\.smali)"')
    for base in ('unica','platform','target'):
        for path in (workspace/base).rglob('*.sh'):
            if path.is_symlink() or not path.resolve().is_relative_to(workspace.resolve()):
                continue
            original=path.read_text()
            text=original
            text=pattern.sub(lambda m:'"$(python3 "$SRC_DIR/integration/smali_paths.py" "$APKTOOL_DIR" "'+m[1]+'" --apktool-absolute)"',text)
            text=text.replace('for f in $FTP; do\n', '''for f in $FTP; do
        if [[ "$f" == */smali/* || "$f" == */smali_classes*/* ]]; then
            f="$(python3 "$SRC_DIR/integration/smali_paths.py" "$APKTOOL_DIR" "$f" --apktool)" || exit 1
        fi
''')
            if text!=original:path.write_text(text)
