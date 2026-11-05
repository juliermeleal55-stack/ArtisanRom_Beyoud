#!/usr/bin/env bash
# Persistent, checkpointed stages of the original Artisan build procedure.
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 /absolute/workspace [dependencies|source|target|firmware|patch|retire|package|rom|alpha]" >&2
    exit 64
fi
workspace=$(realpath "$1")
stage=${2:-rom}
[[ -f "$workspace/BEYOUD-WORKSPACE.json" ]] || { echo 'Not a generated Beyoud workspace' >&2; exit 1; }
[[ -f "$workspace/integration/build.py" ]] || { echo 'Regenerate a fresh workspace with the staged build integration' >&2; exit 1; }
mkdir -p "$workspace/out/beyoud-logs"
log="$workspace/out/beyoud-logs/$stage-$(date +%Y%m%d-%H%M%S).log"
python3 "$workspace/integration/build.py" "$workspace" "$stage" --jobs "${BEYOUD_JOBS:-1}" 2>&1 | tee "$log"
