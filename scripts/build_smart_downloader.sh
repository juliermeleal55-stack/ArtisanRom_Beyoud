#!/usr/bin/env bash
set -euo pipefail
workspace=$(realpath "$1")
[[ -f "$workspace/BEYOUD-WORKSPACE.json" ]] || { echo 'Invalid workspace' >&2; exit 1; }
repo="$workspace/external/samloader-rs"
[[ "$(git -C "$repo" rev-parse HEAD)" == 714d22edad16038f852cfd15903e387d1cd76d9b ]] || { echo 'Unexpected samloader-rs revision' >&2; exit 1; }
mkdir -p "$repo/samloader/examples" "$workspace/out/tools/bin" "$workspace/out/beyoud-logs"
cp "$workspace/integration/samloader/beyoud_probe.rs" "$repo/samloader/examples/beyoud_probe.rs"
set -o pipefail
{
    cargo build --locked --release --manifest-path "$repo/Cargo.toml" -p samloader --bin samloader --example beyoud_probe
    cp "$repo/target/release/samloader" "$workspace/out/tools/bin/samloader-rs"
    cp "$repo/target/release/examples/beyoud_probe" "$workspace/out/tools/bin/beyoud-firmware-probe"
} 2>&1 | tee "$workspace/out/beyoud-logs/smart-downloader-build.log"
