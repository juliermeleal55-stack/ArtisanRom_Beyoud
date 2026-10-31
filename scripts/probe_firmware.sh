#!/usr/bin/env bash
set -eo pipefail
workspace=$(realpath "$1")
[[ -f "$workspace/BEYOUD-WORKSPACE.json" ]] || { echo 'Invalid workspace' >&2; exit 1; }
cd "$workspace"
# Legacy buildenv does not support nounset.
source buildenv.sh beyond2lte
mkdir -p "$OUT_DIR/beyoud-logs"
python3 "$SRC_DIR/integration/samloader/metadata.py" resolve "$workspace" 2>&1 | tee "$OUT_DIR/beyoud-logs/firmware-metadata.log"
