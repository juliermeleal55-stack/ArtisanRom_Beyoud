# SPDX-License-Identifier: GPL-3.0-or-later
"""Install diagnostic-only traversal without weakening production error handling."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install(workspace):
    for relative in ('scripts/utils/module_utils.sh', 'scripts/internal/apply_modules.sh'):
        path = workspace / relative
        if path.read_bytes() != (ROOT / 'reference/build' / relative).read_bytes():
            raise ValueError('Unexpected pinned module runner: ' + relative)
    utils = workspace / 'scripts/utils/module_utils.sh'
    text = utils.read_text()
    call = '    EVAL "LC_ALL=C git apply --directory=\\"$APKTOOL_DIR/$PARTITION/${FILE//system\\//}\\" --verbose --unsafe-paths \\"$PATCH\\"" || return 1'
    if text.count(call) != 1:
        raise ValueError('Unexpected APPLY_PATCH implementation')
    text = text.replace(call, '''    if [[ "${BEYOUD_PATCH_PREFLIGHT:-0}" == "1" ]]; then
        python3 "$SRC_DIR/integration/patch_preflight.py" apply "$SRC_DIR" "$APKTOOL_DIR/$PARTITION/${FILE//system\\//}" "$PATCH" || return 1
    else
''' + call + '\n    fi')
    utils.write_text(text)
    runner = workspace / 'scripts/internal/apply_modules.sh'
    text = runner.read_text()
    anchor = 'if [ "$#" != "1" ]; then'
    text = text.replace(anchor, '''if [[ "${BEYOUD_PATCH_PREFLIGHT:-0}" == "1" && "$#" == "2" && "$1" == "--beyoud-audit-module" ]]; then
    APPLY_MODULE "$2"
    exit 0
fi

''' + anchor, 1)
    call = '    APPLY_MODULE "$f"\ndone < <(find "$1"'
    if text.count(call) != 1:
        raise ValueError('Unexpected module traversal')
    text = text.replace(call, '''    if [[ "${BEYOUD_PATCH_PREFLIGHT:-0}" == "1" ]]; then
        BEYOUD_MODULE_LOG="$SRC_DIR/out/beyoud-logs/patch-preflight-modules/${f#"$SRC_DIR/"}.log"
        mkdir -p "$(dirname "$BEYOUD_MODULE_LOG")"
        if bash "$SRC_DIR/scripts/internal/apply_modules.sh" --beyoud-audit-module "$f" > "$BEYOUD_MODULE_LOG" 2>&1; then
            BEYOUD_MODULE_RESULT=module-passed
        else
            BEYOUD_MODULE_RESULT=module-failed
        fi
        cat "$BEYOUD_MODULE_LOG"
        python3 "$SRC_DIR/integration/patch_preflight.py" "$BEYOUD_MODULE_RESULT" "$SRC_DIR" "$f" "$BEYOUD_MODULE_LOG" || exit 1
    else
        APPLY_MODULE "$f"
    fi
done < <(find "$1"''')
    footer = '\nexit 0\n'
    if not text.endswith(footer):
        raise ValueError('Unexpected module runner footer')
    text = text[:-len(footer)] + '\nif [[ "${BEYOUD_PATCH_PREFLIGHT:-0}" == "1" ]]; then\n    python3 "$SRC_DIR/integration/patch_preflight.py" root "$SRC_DIR" "$1" || exit 1\nfi\n' + footer
    runner.write_text(text)
    make = workspace / 'scripts/make_rom.sh'
    text = make.read_text()
    anchor = '    if [ -d "$APKTOOL_DIR" ]; then'
    if text.count(anchor) != 1:
        raise ValueError('Unexpected APK assembly boundary')
    text = text.replace(anchor, '''    if [[ "${BEYOUD_PATCH_PREFLIGHT:-0}" == "1" ]]; then
        python3 "$SRC_DIR/integration/patch_preflight.py" finish "$SRC_DIR" || exit 1
        exit 0
    fi

''' + anchor)
    make.write_text(text)
