#!/usr/bin/env python3
"""Assemble a candidate Artisan S10 workspace, keeping heavy upstream files out of Git."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import tarfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integration.targets import TARGETS, select

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = '5638a7f66cdf8bc9dd43f087a96f7dfa4f9e6954'
ARCHIVE_SHA256 = 'd755f75a19dc4adc7e0fc2b49553f6e5f03f0eefc69db1e7bb9baf0c7290c39e'
BASE_REPO = 'ArtisanROM-archive/ArtisanROM_old'


def check_archive(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Archive digest differs; do not extract or execute it')


def extract(path, destination):
    with tarfile.open(path, 'r:gz') as archive:
        prefix = f'ArtisanROM_old-{BASE_COMMIT}/'
        for member in archive:
            if member.name.rstrip('/') == prefix.rstrip('/'):
                continue
            if not member.name.startswith(prefix):
                raise ValueError('Unexpected archive root')
            member.name = member.name[len(prefix):]
            output = destination / member.name
            if not output.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Unsafe archive member')
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as src, output.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
                output.chmod(member.mode & 0o777)
            elif member.issym():
                # Android image trees contain absolute runtime symlinks.
                # Preserve them, but never follow them while extracting files.
                output.parent.mkdir(parents=True, exist_ok=True)
                output.symlink_to(member.linkname)
            else:
                raise ValueError('Unsupported archive member type')



def patch_downloader(workspace):
    path = workspace / 'scripts/download_fw.sh'
    text = path.read_text()
    old = 'samloader -m "$MODEL" -r "$CSC" -i "$IMEI" -s "$SERIAL_NO" download$STR -O "$ODIN_DIR/${MODEL}_${CSC}"'
    new = 'python3 "$SRC_DIR/integration/samloader/compat.py" -m "$MODEL" -r "$CSC" download -v "$LATEST_FIRMWARE" -O "$ODIN_DIR/${MODEL}_${CSC}"'
    if text.count(old) != 1:
        raise ValueError('Unexpected legacy downloader invocation')
    text = text.replace(old, new)
    text = text.replace('        #exit 1', '        exit 1')
    # Fail immediately on a rejected package, rather than retrying it eleven times.
    end = '        )\n\n        ZIP_FILE='
    if text.count(end) != 1:
        raise ValueError('Unexpected legacy download error handling')
    text = text.replace(end, '        ) || exit 1\n\n        ZIP_FILE=')
    text = text.replace('        STR=""\n        [ $MODEL == "SM-S731B" ] && STR=" -v S731BXXU1AYH9/S731BOXM1AYH9/S731BXXU1AYH9/S731BXXU1AYH9"\n', '')
    mkdir = '    mkdir -p "$ODIN_DIR/${MODEL}_${CSC}"'
    if mkdir in text:
        text = text.replace(mkdir, mkdir + '\n    find "$ODIN_DIR/${MODEL}_${CSC}" -maxdepth 1 -type f -name "*.zip" -delete')
    path.write_text(text)

def patch_sequential_firmwares(workspace):
    path = workspace / 'scripts/make_rom.sh'
    text = path.read_text()
    start = '    if [ ! -f "$FW_DIR/$SOURCE_FIRMWARE_PATH/.extracted" ] || [ ! -f "$FW_DIR/$TARGET_FIRMWARE_PATH/.extracted" ]; then'
    end = '    LOG_STEP_IN true "Creating work dir"'
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('Unexpected firmware preparation block')
    begin, finish = text.index(start), text.index(end)
    text = text[:begin] + '    python3 "$SRC_DIR/integration/samloader/stage.py" "$SRC_DIR" || exit 1\n\n' + text[finish:]
    path.write_text(text)
    path = workspace / 'scripts/download_fw.sh'
    text = path.read_text()
    # Match the exact pinned upstream command, preserving Odin MD5 validation after it.
    line = next((line for line in text.splitlines() if 'EVAL "unzip -o' in line), None)
    if line is None or text.count(line) != 1:
        raise ValueError('Unexpected ZIP expansion command')
    text = text.replace(line, '    python3 "$SRC_DIR/integration/samloader/unpack_reclaim.py" "$ZIP_FILE" "$ODIN_DIR/${MODEL}_${CSC}" || exit 1')
    path.write_text(text)


def patch_firmware_lookup(workspace):
    path = workspace / 'scripts/utils/firmware_utils.sh'
    text = path.read_text()
    replacement = '''GET_LATEST_FIRMWARE()
{
    python3 "$SRC_DIR/integration/samloader/metadata.py" get "$OUT_DIR/firmware-lock.json" "$1" "$2"
}'''
    text, count = re.subn(r'GET_LATEST_FIRMWARE\(\)\n\{.*?\n\}', lambda _: replacement, text, flags=re.S)
    if count != 1:
        raise ValueError('Unexpected firmware lookup helper')
    path.write_text(text)


def patch_parallel_builds(workspace):
    # wait PID1 PID2 returns only the last status: a failed earlier worker was hidden.
    for relative, count in [('scripts/make_rom.sh', 1), ('scripts/internal/build_flashable_zip.sh', 2)]:
        path = workspace / relative
        text = path.read_text()
        old = 'wait $(jobs -p) || exit 1'
        if text.count(old) != count:
            raise ValueError(f'Unexpected parallel build schema: {relative}')
        wait = '''BEYOUD_FAILED=0
for BEYOUD_PID in "${BEYOUD_PIDS[@]}"; do
    wait "$BEYOUD_PID" || BEYOUD_FAILED=1
done
[ "$BEYOUD_FAILED" -eq 0 ] || exit 1'''
        text = text.replace(old, wait)
        if relative.endswith('make_rom.sh'):
            old_hash = 'find "$SRC_DIR/unica" "$SRC_DIR/target/$TARGET_CODENAME" -type f -print0'
            new_hash = 'find "$SRC_DIR/unica" "$SRC_DIR/target/$TARGET_CODENAME" "$SRC_DIR/platform/$TARGET_PLATFORM" "$SRC_DIR/integration" "$OUT_DIR/firmware-lock.json" -type f -print0'
            text = text.replace(old_hash, new_hash)
        if relative.endswith('make_rom.sh'):
            start = '        while IFS= read -r f; do'
            end = '        done < <(find "$APKTOOL_DIR"'
            if text.count(start) != 1 or text.count(end) != 1:
                raise ValueError('Unexpected APK worker loop')
            text = text.replace(start, '        BEYOUD_PIDS=()\n' + start)
            text = text.replace(end, '            BEYOUD_PIDS+=("$!")\n' + end)
        else:
            if text.count('while IFS= read -r f; do') < 2 or text.count('    ) &\ndone') != 2:
                raise ValueError('Unexpected partition worker loops')
            # Only the two top-level build/compression loops, not loops in helper functions.
            text = text.replace('\nwhile IFS= read -r f; do', '\nBEYOUD_PIDS=()\nwhile IFS= read -r f; do')
            text = text.replace('    ) &\ndone', '    ) &\n    BEYOUD_PIDS+=("$!")\ndone')
        path.write_text(text)


def apply_overlay(workspace, codename="beyond2lte"):
    device = select(codename)
    model = device["model"]
    shutil.copytree(ROOT / 'integration', workspace / 'integration')
    shutil.copyfile(ROOT / 'integration/artisan/essi_64.sh',
                    workspace / 'unica/configs/essi_64.sh')
    kernel_module = workspace / 'platform/exynos9820/patches/extremekrnl/customize.sh'
    kernel_module.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'integration/artisan/extremekrnl.sh', kernel_module)
    patch_downloader(workspace)
    patch_firmware_lookup(workspace)
    patch_parallel_builds(workspace)
    patch_sequential_firmwares(workspace)
    target = workspace / 'target' / codename / 'config.sh'
    text = target.read_text()
    expected = f'TARGET_ASSERT_MODEL=("{model}" "{device["legacy_model"]}")'
    if expected not in text or f'TARGET_CODENAME="{codename}"' not in text:
        raise ValueError('Unexpected base device configuration')
    text = text.replace(expected, f'TARGET_ASSERT_MODEL=("{model}")')
    text = text.replace('TARGET_EXTRA_FIRMWARES=("")', 'TARGET_EXTRA_FIRMWARES=()')
    target.write_text(text)
    version = workspace / 'unica/configs/version.sh'
    if version.exists():
        with version.open('a') as stream:
            stream.write('\n# Unofficial test candidate, not an ArtisanROM release.\nROM_VERSION="0.1.0-alpha1"\nROM_CODENAME="Beyoud"\n')
    (workspace / 'BEYOUD-WORKSPACE.json').write_text(json.dumps({
        'base_commit': BASE_COMMIT, 'status': 'unvalidated-candidate',
        'target': model, 'codename': codename, 'flashable_release': False,
        'donor_commit': '609fa7cc738e42dedcc31ffecbe4aefc0b34d6e2',
        'note': 'Legacy framework patches retained for compatibility investigation; not migrated.'
    }, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--target', choices=sorted(TARGETS), default='beyond2lte')
    parser.add_argument('--archive', type=Path, help='Previously downloaded pinned archive')
    parser.add_argument('--discard-archive', action='store_true', help='Delete only the automatically managed archive after successful assembly')
    args = parser.parse_args()
    if args.discard_archive and args.archive is not None:
        parser.error('--discard-archive cannot delete a user-supplied --archive')
    destination = args.destination.resolve()
    if destination.exists():
        parser.error('Destination must not exist; existing work is never overwritten')
    if destination == ROOT or ROOT in destination.parents:
        parser.error('Use a workspace OUTSIDE the repository')
    archive = args.archive or destination.parent / f'artisan-{BASE_COMMIT}.tar.gz'
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['curl', '--fail', '--location', '--retry', '2',
                        f'https://codeload.github.com/{BASE_REPO}/tar.gz/{BASE_COMMIT}',
                        '-o', str(archive)], check=True)
    check_archive(archive)
    destination.mkdir(parents=True)
    extract(archive, destination)
    apply_overlay(destination, args.target)
    if args.discard_archive:
        archive.unlink()
    print(f'Candidate assembled: {destination}')
    print('External submodules are NOT included in the archive. See docs/INTEGRATION.md.')


if __name__ == '__main__':
    main()
