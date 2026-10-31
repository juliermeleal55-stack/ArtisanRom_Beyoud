#!/usr/bin/env bash
# Execute the original Artisan pipeline in the generated candidate workspace.
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 /absolute/candidate/workspace [dependencies|rom|alpha]" >&2
    exit 64
fi
workspace=$(realpath "$1")
stage=${2:-rom}
[[ "$stage" == dependencies || "$stage" == rom || "$stage" == alpha ]] || { echo 'Invalid stage' >&2; exit 64; }
[[ -f "$workspace/BEYOUD-WORKSPACE.json" ]] || { echo 'Not a generated Beyoud workspace' >&2; exit 1; }
mkdir -p "$workspace/out/beyoud-logs"
log="$workspace/out/beyoud-logs/$stage-$(date +%Y%m%d-%H%M%S).log"
(
    cd "$workspace"
    # Legacy envsetup reads unset variables: do not impose nounset on upstream.
    set +u
    source buildenv.sh beyond2lte
    if [[ "$stage" == dependencies ]]; then
        ./scripts/build_dependencies.sh
    elif [[ "$stage" == alpha ]]; then
        echo "EXPERIMENTAL ALPHA: no boot or hardware validation; not for daily use."
        ./scripts/make_rom.sh
    else
        # No flashable ZIP until kernel/vendor/framework compatibility is validated.
        ./scripts/make_rom.sh --no-rom-zip
    fi
) 2>&1 | tee "$log"
