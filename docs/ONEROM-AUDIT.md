# OneROM audit and controlled integration — 2026-11-05

## Immutable source and scope

- Repository: https://github.com/DaDevMikey/OneROM
- Branch inspected: `seventeen`
- Pinned commit: `644f0aacc49ad2410e566de8deb05e6c8211d83d`
- Full recursive Git tree returned without truncation: 4,468 files,
  2,169,646,717 bytes of listed blobs (not compressed download size).
- Compared by Git blob ID against our pinned Artisan archive
  `5638a7f66cdf8bc9dd43f087a96f7dfa4f9e6954`.
- 37 small textual evidence/module files imported with exact Git blob IDs and
  sizes in `manifests/onerom.json`. Upstream LICENSE and original headers kept.
- This is a source/architecture review, not verification of upstream runtime
  claims, release binaries, every smali hunk, or physical device compatibility.

| Scope | OneROM files | Identical to Artisan | Changed existing | New |
|---|---:|---:|---:|---:|
| platform/exynos9820 | 241 | 233 | 6 | 2 |
| target/beyond1lte | 233 | 8 | 4 | 221 |
| target/beyond2lte | 0 | 0 | 0 | 0 |
| scripts | 20 | 9 | 10 | 1 |
| unica | 2,590 | 2,554 | 28 | 8 |
| prebuilts | 1,345 | 1,279 | 60 | 6 |

The identical platform files show that copying everything is not equivalent to
adding missing hardware support. Much is already inherited from our base. The
prebuilts alone account for ~1.75 GB; no bulk binary import was performed.

## Architecture differences that prevent a wholesale merge

OneROM's README claims native One UI 9 / Android 17 support for **beyond1lte**,
not beyond2lte. Its `r12s_native.sh` selects **SM-S721B/EUX/S721BXXSFEZJ1**
(Galaxy S24 FE), API 37, and no separate source system_ext. Our approved setup
remains historical Artisan S10 + the pinned UN1CA donor adapter (SM-S926B/EUX).
The UI name and actual SDK of our downloaded donor are still unverified.

OneROM's S10 config also changes MDNIE, hotspot/audio flags and display density.
These are not proof the S10+ has those capabilities. We retain our own target
assertions, stock firmware, partition settings, overlays and kernel procedure.

The README advertises bundled OneKernel binaries and another source reference;
the platform kernel script points at a different M62-backport repository and is
**disabled**. README attribution is not proof that a particular prebuilt matches
reproducible source. We did not import kernel images, overclocking, root-manager
changes, or replace our pinned source-built kernel with these binaries.

## Integrated into generated workspaces (both Exynos targets)

1. **Bluetooth legacy path is gated by the actual extracted donor SDK.**
   OneROM avoids replacing Bluetooth with the old b0sxxx APEX and applying its
   JNI byte patch on API >=37. We adapt that decision but read the immutable
   extracted source build.prop, not only the declared SDK in a config file.
   Unknown/duplicate/missing SDK data stops the module; it is not assumed to be
   37. API <37 keeps the exact existing Artisan APEX/hex patch and procedure;
   API >=37 preserves the newer donor stack. This is not a Bluetooth fix claim.
2. **Legacy vendor initialization module**, after the existing vendor module:
   imports `/vendor/ueventd.rc` into the system ueventd configuration once;
   fixes missing final newline in vendor property contexts; adds the RIL path
   context only when the stock policy declares `vendor_rild_prop` and no mapping
   already exists. Existing mappings, file permissions and metadata maps remain.
   Missing required files fail before changes; no invented SELinux types,
   disabled security checks or insecure ADB defaults are introduced.
3. Workspace provenance records the OneROM pin, active adaptations and staged
   modules. Assembly verifies every imported reference and refuses collisions
   or unexpected Bluetooth-script anchors instead of overwriting silently.

## Imported but deliberately NOT activated

These four modules are copied into **beyond1lte only**, including their upstream
`disable` files. The original Artisan module loader recognizes that marker.
They are reference candidates, not enabled fixes:

- `search_indexing`: handles an absent (-1) policy resource identifier in
  SecSettingsIntelligence; requires the matching donor implementation.
- `usb_initialization`: changes services.jar's legacy sec_charging/MTP startup
  state handling; requires matching smali and runtime USB role testing.
- `wallpaper_capture`: DressRoom nullable capture callback fallback, explicitly
  tied to a specific app/version and obfuscated classes.
- `user_defaults`: software A2DP settings/defaults; includes smali, init script
  and user-setting policy, not merely an isolated property toggle.

Do not delete the disable markers just to get features. First trace the actual
SM-S926B APK/JAR code, adapt each patch, validate DEX and test the behavior. No
such donor-specific validation has been completed in this session.

## Important missing work identified, not silently imported

OneROM's product_abilist module is a large interconnected hardware/runtime port:

- ARM64-only zygote plus isolated legacy 32-bit linker/HAL runtime;
- audio, SoundTrigger, camera, OMX and Bluetooth wrapper dependencies;
- `libui`/gralloc2 compatibility binaries and shim assembly;
- donor-specific native and smali patches for Settings/framework;
- S10 thermal/DVFS policies and SDHMS resources;
- netbpfload/connectivity/netd changes for an old 4.14 kernel;
- libstagefright binary changes and security-service removals.

The script includes hardcoded SM-G973F properties/OneROM branding, binary byte
patterns and donor-specific APK/resource layouts. Copying it would either fail
on our donor or apply unverified boot/security changes. It is imported as text
for review but NOT executed or installed as an active module. Matching source,
ELF dependencies/ABIs, firmware versions and kernel requirements must be checked
before enabling any of this. We do not spoof kernel support or remove services
as a substitute for that validation.

The changed camera script catches failed libstagefright HEX_PATCH calls and logs
a warning instead of stopping. We deliberately do NOT import that behavior: a
missing binary signature requires donor-specific investigation, not an ignored
patch failure. The older Bluetooth byte signature is likewise preserved for
the legacy branch, rather than replaced with OneROM's different bytes.

Extra Dim is also disabled upstream and depends on donor smali. Camera's generic
platform module remains largely inherited; its target overlays must stay
separate for S10 and S10+. Changes to extraction/ZIP scripts and donor layout are
not substituted for our existing CRC/MD5, sequential downloads or original ZIP
procedure. OneROM does not establish that our hosted disk peak is solved.

Upstream's README includes destructive userdata-formatting instructions. Those
are NOT adopted or recommended for our candidate; no recovery/format operation
was executed. Its hardware claims remain upstream claims, not our test results.

## Local validation and remaining acceptance criteria

- Unit tests execute transformed Bluetooth branches with actual extracted SDK
  fixtures (including disagreement with declared SDK), and syntax-check the
  complete transformed pinned legacy script.
- Tests cover init idempotence, pre-existing imports/mappings, missing SELinux
  types, required-input failure, preservation of modes, target scoping and
  preservation of all four disable markers.
- Reference verifier checks both Artisan and OneROM text integrity.
- No full firmware/ROM build, kernel run, flash or physical boot was performed.
  No new ZIP or One UI 9 compatibility is claimed. Storage remains unresolved.
