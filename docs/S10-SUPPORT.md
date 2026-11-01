# Galaxy S10 normal — candidate Exynos support

Added target: **beyond1lte / SM-G973F**. This is not support for SM-G973U/U1/W/0
or other Snapdragon variants. The user's exact model has not yet been confirmed.
SM-G973N is also deliberately excluded from assertions until separately validated.

The pinned ArtisanROM archive already includes its own beyond1lte tree, overlays,
camera modules, sff.sh and postinstall. The preparer preserves that tree instead
of cloning the S10+ target. Stock firmware remains SM-G973F/AUT, Exynos 9820,
vendor API/VNDK 31, static ext4, 60 Hz. Platform patches and the donor adapter
are shared with the Exynos S10+, but the kernel build receives beyond1lte.

```bash
python3 scripts/prepare_workspace.py /outside/repo/s10-work --target beyond1lte
python3 scripts/init_workspace_dependencies.py /outside/repo/s10-work
bash scripts/build_smart_downloader.sh /outside/repo/s10-work
bash scripts/probe_firmware.sh /outside/repo/s10-work
bash scripts/build_candidate.sh /outside/repo/s10-work dependencies
bash scripts/build_candidate.sh /outside/repo/s10-work alpha
python3 scripts/collect_alpha.py /outside/repo/s10-work /outside/repo/s10-result
python3 scripts/port.py doctor --target beyond1lte
```

Default CLI target remains beyond2lte/SM-G975F. Generated markers now contain
model AND codename. Wrappers reject mismatched/unknown markers; legacy G975F
markers remain readable. Package names and model assertions are device-specific,
so a G973F archive is rejected by the G975F collector and vice versa.

The alpha workflow is now **manual** (workflow_dispatch) with a target selector,
to avoid automatically starting expensive firmware builds just by changing the
workflow. Source validation still runs on pushes and pull requests. No phone
firmware build was launched as part of adding this unconfirmed target.

Validation in this step: unit tests for own stock configuration, target routing,
model mismatch rejection, legacy markers, distinct package names and warnings.
This does not validate firmware download, patch application or physical boot.
The existing storage/extraction problems and unverified donor properties also
apply to this target. No flashable S10 ROM is claimed.
