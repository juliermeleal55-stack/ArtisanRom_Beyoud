#!/usr/bin/env python3
"""Assemble a candidate Artisan S10 workspace, keeping heavy upstream files out of Git."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

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
    path.write_text(text)

def apply_overlay(workspace):
    shutil.copytree(ROOT / 'integration', workspace / 'integration')
    shutil.copyfile(ROOT / 'integration/artisan/essi_64.sh',
                    workspace / 'unica/configs/essi_64.sh')
    kernel_module = workspace / 'platform/exynos9820/patches/extremekrnl/customize.sh'
    kernel_module.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'integration/artisan/extremekrnl.sh', kernel_module)
    patch_downloader(workspace)
    target = workspace / 'target/beyond2lte/config.sh'
    text = target.read_text()
    if 'TARGET_ASSERT_MODEL=("SM-G975F" "SM-G975N")' not in text:
        raise ValueError('Unexpected base device configuration')
    text = text.replace('TARGET_ASSERT_MODEL=("SM-G975F" "SM-G975N")',
                        'TARGET_ASSERT_MODEL=("SM-G975F")')
    text = text.replace('TARGET_EXTRA_FIRMWARES=("")', 'TARGET_EXTRA_FIRMWARES=()')
    target.write_text(text)
    version = workspace / 'unica/configs/version.sh'
    if version.exists():
        with version.open('a') as stream:
            stream.write('\n# Unofficial test candidate, not an ArtisanROM release.\nROM_VERSION="0.1.0-alpha1"\nROM_CODENAME="Beyoud"\n')
    (workspace / 'BEYOUD-WORKSPACE.json').write_text(json.dumps({
        'base_commit': BASE_COMMIT, 'status': 'unvalidated-candidate',
        'target': 'SM-G975F', 'flashable_release': False,
        'donor_commit': '609fa7cc738e42dedcc31ffecbe4aefc0b34d6e2',
        'note': 'Legacy framework patches retained for compatibility investigation; not migrated.'
    }, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--archive', type=Path, help='Previously downloaded pinned archive')
    args = parser.parse_args()
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
    apply_overlay(destination)
    print(f'Candidate assembled: {destination}')
    print('External submodules are NOT included in the archive. See docs/INTEGRATION.md.')


if __name__ == '__main__':
    main()
