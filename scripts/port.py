#!/usr/bin/env python3
"""Inspect pinned sources without executing upstream build scripts."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKS = (
    "hardware_confirmed", "donor_firmware_verified", "kernel_validated",
    "partition_layout_verified", "vendor_compatibility_validated", "boot_validated",
)


def load_manifest():
    data = json.loads((ROOT / "manifests/upstreams.json").read_text())
    for source in data["sources"].values():
        if not re.fullmatch(r"[0-9a-f]{40}", source["commit"]):
            raise ValueError("Upstream must be pinned to a full commit")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", source["repository"]):
            raise ValueError("Invalid repository")
    return data


def doctor(profile):
    missing = [key for key in CHECKS if profile.get(key) is not True]
    if profile.get("status") != "validated" or profile.get("flashable") is not True:
        missing.append("release_validated")
    return missing


def inspect(destination):
    """Fetch small textual evidence via gh, not firmware or executable dependencies."""
    paths = {
        "un1ca": ["README.md", "LICENSE", "unica/configs/essi.sh",
                  "target/y2slte/config.sh", "buildenv.sh", "INSTRUCTIONS.md"],
        "artisan_current": ["README.md", "LICENSE", "target/y2s/config.sh"],
        "artisan_s10": ["README.md", "LICENSE", "target/beyond2lte/config.sh"],
        "extremekernel": ["build.sh", "Makefile"],
    }
    destination = destination.resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise ValueError("Save upstream evidence outside the project repository")
    for name, source in load_manifest()["sources"].items():
        for path in paths[name]:
            result = subprocess.run(
                ["gh", "api", f'repos/{source["repository"]}/contents/{path}'
                 f'?ref={source["commit"]}', "-H", "Accept: application/vnd.github.raw+json"],
                check=True, capture_output=True, timeout=60,
            )
            output = destination / name / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(result.stdout)
            print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report readiness; nonzero means NOT flashable")
    audit = commands.add_parser("inspect", help="Fetch pinned reference text using gh")
    audit.add_argument("destination", type=Path)
    args = parser.parse_args()
    load_manifest()
    if args.command == "inspect":
        inspect(args.destination)
        return 0
    profile = json.loads((ROOT / "devices/beyond2lte/port.json").read_text())
    missing = doctor(profile)
    print(f'{profile["codename"]}: ' + ("BLOQUEADO — não instalar" if missing else "Checklist preenchido; requer revisão humana"))
    for item in missing:
        print(f"  PENDENTE: {item}")
    return 2 if missing else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)
