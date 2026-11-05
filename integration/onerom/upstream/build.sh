#!/usr/bin/env bash
#
# OneROM Delta 9.0 Build Helper
#

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "=========================================================="
echo " Starting OneROM Delta 9.0 Build for Galaxy S10 (beyond1lte)"
echo " Source Donor: Galaxy S24 FE (SM-S721B / r12s)"
echo " Target Base: ArtisanROM Exynos 9820 HALs / Kernel"
echo " Build Engine: ExtremeROM sixteen / UN1CA Native"
echo "=========================================================="

source buildenv.sh beyond1lte

bash scripts/make_rom.sh "$@"
