#!/usr/bin/env bash
set -eo pipefail
workspace=$(realpath "$1")
[[ -f "$workspace/BEYOUD-WORKSPACE.json" ]] || { echo 'Invalid workspace' >&2; exit 1; }
cd "$workspace"
# Legacy buildenv does not support nounset.
source buildenv.sh beyond2lte
mkdir -p "$OUT_DIR/beyoud-logs"
{
    for firmware in "$SOURCE_FIRMWARE" "$TARGET_FIRMWARE"; do
        IFS=/ read -r model csc ignored <<< "$firmware"
        # Deliberately discard the inherited third field: SmartDownload needs no IMEI.
        timeout 180 "$TOOLS_DIR/bin/beyoud-firmware-probe" "$model" "$csc"
    done
} 2>&1 | tee "$OUT_DIR/beyoud-logs/firmware-metadata.log"
