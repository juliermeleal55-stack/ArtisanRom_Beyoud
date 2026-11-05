# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict transformations of the pinned Artisan scripts; refuse schema drift."""
from pathlib import Path
import re


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Unexpected pinned build anchor: {old[:90]}')
    return text.replace(old, new)


def bound_workers(text):
    append = 'BEYOUD_PIDS+=("$!")'
    if not text.count(append):
        raise ValueError('No tracked worker loops')
    barrier = '''BEYOUD_PIDS+=("$!")
            if [ "${#BEYOUD_PIDS[@]}" -ge "${BEYOUD_JOBS:-1}" ]; then
                BEYOUD_FAILED=0
                for BEYOUD_PID in "${BEYOUD_PIDS[@]}"; do
                    wait "$BEYOUD_PID" || BEYOUD_FAILED=1
                done
                [ "$BEYOUD_FAILED" -eq 0 ] || exit 1
                BEYOUD_PIDS=()
            fi'''
    return text.replace(append, barrier)


def zip_policy(text):
    # Static S10 partitions do not need all images alive for dynamic group sizing.
    # Convert/compress each image immediately; retain the original dynamic path.
    quality = 'BROTLI_QUALITY=6\n$DEBUG && BROTLI_QUALITY=0\n'
    text = once(text, quality, '')
    marker = 'LOG_STEP_IN "- Building OS partitions"'
    helper = '''BROTLI_QUALITY=6
$DEBUG && BROTLI_QUALITY=0
BEYOUD_COMPRESS_PARTITION()
{
    local f="$1"
    local PARTITION="$(basename "$f" .img)"
    EVAL "img2sdat -o \\"$TMP_DIR\\" \\"$f\\"" || return 1
    rm -f "$f"
    EVAL "brotli --quality=\\"$BROTLI_QUALITY\\" --output=\\"$TMP_DIR/$PARTITION.new.dat.br\\" \\"$TMP_DIR/$PARTITION.new.dat\\"" || return 1
    rm -f "$TMP_DIR/$PARTITION.new.dat"
}

'''
    text = once(text, marker, helper + marker)
    anchor = '"$WORK_DIR/$PARTITION" "$WORK_DIR/configs/file_context-$PARTITION" "$WORK_DIR/configs/fs_config-$PARTITION" || exit 1\n        LOG_STEP_OUT'
    text = once(text, anchor, anchor.replace('\n        LOG_STEP_OUT', '''
        if [ "$TARGET_SUPER_PARTITION_SIZE" -eq 0 ]; then
            python3 "$SRC_DIR/integration/package_inputs.py" check-image "$SRC_DIR" "$PARTITION" "$TMP_DIR/$PARTITION.img" || exit 1
            BEYOUD_COMPRESS_PARTITION "$TMP_DIR/$PARTITION.img" || exit 1
        fi
        LOG_STEP_OUT'''))
    text = once(text, 'source \"$SRC_DIR/scripts/utils/build_utils.sh\" || exit 1', 'source \"$SRC_DIR/scripts/utils/build_utils.sh\" || exit 1\npython3 \"$SRC_DIR/integration/package_inputs.py\" verify \"$SRC_DIR\" || exit 1')
    # No package code may read deleted firmware trees: compact identifiers are
    # captured and checked against the firmware lock by the staged orchestrator.
    source = '$(GET_PROP "$FW_DIR/$SOURCE_FIRMWARE_PATH/system/system/build.prop" "ro.build.product")'
    vendor = '$(GET_PROP "$FW_DIR/$SOURCE_FIRMWARE_PATH/vendor/build.prop" "ro.product.vendor.device")'
    target = '$(GET_PROP "$FW_DIR/$TARGET_FIRMWARE_PATH/system/system/build.prop" "ro.build.product")'
    target_vendor = '$(GET_PROP "$FW_DIR/$TARGET_FIRMWARE_PATH/vendor/build.prop" "ro.product.vendor.device")'
    for old, key in [(source, 'source_product'), (vendor, 'source_vendor'), (target, 'target_product'), (target_vendor, 'target_vendor')]:
        new = '$(python3 "$SRC_DIR/integration/package_inputs.py" get "$SRC_DIR" ' + key + ')'
        text = once(text, old, new)
    return text


def stream_lz4(text):
    start = '        EVAL "tar xf \\"$TAR\\" -C \\"$FW_DIR/${MODEL}_${CSC}\\" \\"$FILE.lz4\\"" || return 1'
    end = '        EVAL "lz4 -d --rm \\"$FW_DIR/${MODEL}_${CSC}/$FILE.lz4\\" \\"$FW_DIR/${MODEL}_${CSC}/$FILE\\"" || return 1'
    text = once(text, start, '''        # Stream the compressed member: do not retain a second .lz4 copy.
        if ! (set -o pipefail
            tar -xOf "$TAR" "$FILE.lz4" | lz4 -d -c > "$FW_DIR/${MODEL}_${CSC}/$FILE.beyoud-partial"
        ); then
            rm -f "$FW_DIR/${MODEL}_${CSC}/$FILE.beyoud-partial"
            return 1
        fi''')
    return once(text, end, '''        [ -s "$FW_DIR/${MODEL}_${CSC}/$FILE.beyoud-partial" ] || return 1
        mv -f "$FW_DIR/${MODEL}_${CSC}/$FILE.beyoud-partial" "$FW_DIR/${MODEL}_${CSC}/$FILE" || return 1''')


def partition_policy(text):
    begin = '    local PARTITION\n    for f in $FILES; do\n'
    finish = '\n    LOG_STEP_OUT\n}\n\nGET_IMAGE_FILE_SYSTEM()'
    if text.count(begin) != 1 or text.count(finish) != 1:
        raise ValueError('Unexpected OS extraction loop')
    a, b = text.index(begin), text.index(finish)
    loop = text[a:b]
    head = '    local PARTITION\n    for f in $FILES; do\n'
    if not loop.endswith('    done\n'):
        raise ValueError('Unexpected OS extraction loop ending')
    body = loop[len(head):-len('    done\n')]
    body = once(body, '[ -f "$FW_DIR/${MODEL}_${CSC}/$f" ] || continue', '[ -f "$FW_DIR/${MODEL}_${CSC}/$f" ] || return 0')
    function = '''BEYOUD_UNPACK_PARTITION()
{
    local f="$1"
    local PARTITION
''' + body + '}\n\n'
    text = text[:a] + '    for f in $FILES; do\n        BEYOUD_UNPACK_PARTITION "$f" || exit 1\n    done\n' + text[b:]
    text = once(text, 'EXTRACT_OS_PARTITIONS()\n', function + 'EXTRACT_OS_PARTITIONS()\n')
    text = once(text, '    LOG_STEP_IN \"- Extracting OS partitions\"', '    local BEYOUD_SUPER_PARTITIONS=\"\"\n    LOG_STEP_IN \"- Extracting OS partitions\"')
    # Keep metadata and all partitions, but unpack and release each child image
    # before lpunpack produces the next one. Never punch the shared super image.
    anchor = '        for p in $(grep "partition_list"'
    text = once(text, anchor, '        BEYOUD_SUPER_PARTITIONS="$(grep "partition_list" "$FW_DIR/${MODEL}_${CSC}/os_partitions_metadata.txt" | cut -d "=" -f 2 -s)"\n' + anchor)
    end = '            fi\n        done\n\n        rm -f "$FW_DIR/${MODEL}_${CSC}/super.img"'
    text = once(text, end, '            fi\n            BEYOUD_UNPACK_PARTITION "${p}.img" || exit 1\n        done\n\n        rm -f "$FW_DIR/${MODEL}_${CSC}/super.img"')
    anchor = '    for f in $FILES; do\n        [ -f "$FW_DIR/${MODEL}_${CSC}/$f" ] && continue'
    text = once(text, anchor, '''    for f in $FILES; do
        case " ${BEYOUD_SUPER_PARTITIONS:-} " in *" ${f%.img} "*) continue ;; esac
        [ -f "$FW_DIR/${MODEL}_${CSC}/$f" ] && continue''')
    return text


def debloat_workers(text):
    pattern = r'\[ "\$(?P<name>[A-Z_]+_DEBLOAT)" \] && (?P<command>xargs[^\n]*\n[^\n]*\n[ \t]*<<< "\$(?P=name)")'
    def replacement(match):
        command = match['command'].replace('$(nproc)', '${BEYOUD_JOBS:-1}')
        return f'if [ -n "${match["name"]}" ]; then\n    {command} || exit 1\nfi'
    result, count = re.subn(pattern, replacement, text)
    if count != 7:
        raise ValueError('Unexpected seven-partition debloat worker schema')
    return result.rstrip() + '\nreturn 0\n'


def apply(workspace):
    make = workspace / 'scripts/make_rom.sh'
    zip_file = workspace / 'scripts/internal/build_flashable_zip.sh'
    fw_utils = workspace / 'scripts/utils/firmware_utils.sh'
    extract = workspace / 'scripts/extract_fw.sh'
    # Validate all transforms before writing any scripts.
    make_text = bound_workers(make.read_text())
    cleanup = 'if [ -n "$GITHUB_ACTIONS" ]; then\n    bash "$SRC_DIR/scripts/cleanup.sh" fw kernel\nfi\n\n'
    make_text = once(make_text, cleanup, '')
    # Firmware identifiers are still needed by older direct ZIP users. Cleanup
    # is controlled by the verified prune stage, never by ambient CI variables.
    outputs = {make: make_text, zip_file: zip_policy(bound_workers(zip_file.read_text())),
               fw_utils: stream_lz4(fw_utils.read_text()), extract: partition_policy(extract.read_text())}
    config = workspace / 'scripts/internal/gen_config_file.sh'
    outputs[config] = once(config.read_text(), 'GET_BUILD_VAR "ROM_BUILD_TIMESTAMP" "$(date +%s)"',
                           'GET_BUILD_VAR "ROM_BUILD_TIMESTAMP" "${BEYOUD_BUILD_TIMESTAMP:-$(date +%s)}"')
    # Bound the pinned host scripts' explicit nproc parallelism too. Third-party
    # nested build systems remain separately audited rather than silently edited.
    for path in list((workspace / 'scripts').rglob('*.sh')) + [workspace / 'external/make.sh']:
        if path.is_file():
            content = outputs.get(path, path.read_text())
            outputs[path] = content.replace('$(nproc --all)', '${BEYOUD_JOBS:-1}').replace('$(nproc)', '${BEYOUD_JOBS:-1}')
    debloat = workspace / 'unica/patches/debloat/customize.sh'
    anchor = 'ODM_DEBLOAT="$(sed'
    command = 'python3 "$SRC_DIR/integration/debloat.py" "$OUT_DIR/beyoud-logs/debloat-plan.json"'
    for partition in ('ODM', 'PRODUCT', 'SYSTEM', 'SYSTEM_EXT', 'VENDOR', 'PRISM', 'OPTICS'):
        command += f' "${{{partition}_DEBLOAT:-}}"'
    outputs[debloat] = debloat_workers(once(debloat.read_text(), anchor, command + ' || exit 1\n\n' + anchor))
    for path, content in outputs.items():
        path.write_text(content)
