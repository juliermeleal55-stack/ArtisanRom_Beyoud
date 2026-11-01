#!/usr/bin/env bash
# Only for a disposable GitHub-hosted runner. Never run general cleanup on a user's Linux host.
set -euo pipefail
[[ ${BEYOUD_HOSTED_RUNNER:-0} == 1 && ${GITHUB_ACTIONS:-} == true ]] || {
    echo 'Storage cleanup refused: requires explicit disposable hosted-runner opt-in.' >&2
    exit 1
}
echo 'Storage before cleanup:'
df -h
# Preserve Java, Python, Go, Rust and compiler installations used by this pipeline.
for path in /usr/local/lib/android /usr/share/dotnet /opt/ghc /usr/local/.ghcup \
    /opt/hostedtoolcache/CodeQL /usr/local/share/powershell /usr/local/share/chromium \
    /opt/google/chrome /opt/microsoft/msedge /usr/share/swift /opt/az \
    /home/runner/.cache/ms-playwright; do
    if [[ -e "$path" ]]; then
        sudo du -sh "$path"
        sudo rm -rf -- "$path"
    fi
done
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
    docker image prune --all --force
    docker builder prune --all --force
fi
sudo apt-get clean
echo 'Storage after cleanup:'
df -h
