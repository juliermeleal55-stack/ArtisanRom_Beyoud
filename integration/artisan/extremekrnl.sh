# SPDX-License-Identifier: GPL-3.0-or-later
# Replacement for the historical floating-branch ExtremeKernel module.
# Retains the original build command and image destinations.
REPLACE_PINNED_KERNEL_BINARIES()
{
    local kernel_dir="$KERNEL_TMP_DIR-$TARGET_PLATFORM"
    local revision="9a0a792d227c8ae6cddac0c9d68a8bb9782c44cb"
    local repository="https://github.com/Android-Artisan/android_kernel_samsung_exynos9820"
    if [[ ! -d "$kernel_dir/.git" ]]; then
        [[ ! -d "$kernel_dir" ]] || [[ -z "$(ls -A "$kernel_dir")" ]] || ABORT "Kernel directory is not empty"
        (
            set -e
            git init "$kernel_dir"
            git -C "$kernel_dir" remote add origin "$repository"
            git -C "$kernel_dir" fetch --depth=1 origin "$revision"
            git -C "$kernel_dir" checkout --detach "$revision"
            git -C "$kernel_dir" submodule update --init --recursive
        ) || ABORT "Cannot initialize pinned ExtremeKernel"
    fi
    [[ "$(git -C "$kernel_dir" rev-parse HEAD)" == "$revision" ]] || ABORT "Unexpected kernel revision; use a fresh work directory"
    [[ -z "$(git -C "$kernel_dir" status --porcelain)" ]] || ABORT "Kernel source contains local changes"
    (
        set -e
        local_driver=$(mktemp "$kernel_dir/.beyoud-build.XXXXXX.sh") || exit 1
        trap 'rm -f "$local_driver"' EXIT
        python3 "$SRC_DIR/integration/kernel_budget.py" "$kernel_dir/build.sh" "$local_driver" || exit 1
        cd "$kernel_dir" || exit 1
        bash "$local_driver" -m "$TARGET_CODENAME" -k y -r n
    ) || ABORT "Kernel build failed"
    local image
    for image in boot dtb dtbo; do
        [[ -s "$kernel_dir/build/out/$TARGET_CODENAME/$image.img" ]] || ABORT "Kernel image missing: $image"
    done
    mkdir -p "$WORK_DIR/kernel"
    for image in boot dtb dtbo; do
        cp "$kernel_dir/build/out/$TARGET_CODENAME/$image.img" "$WORK_DIR/kernel/$image.img" || ABORT "Cannot copy $image"
    done
}
REPLACE_PINNED_KERNEL_BINARIES
