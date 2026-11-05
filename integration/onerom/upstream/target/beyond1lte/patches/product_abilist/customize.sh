# eux
SET_PROP "vendor" "ro.zygote" "zygote64"

# Display Density & Scaling (lock across all partitions to prevent reboot shrinking)
for part in system vendor product odm; do
    SET_PROP "$part" "ro.sf.lcd_density" "$TARGET_LCD_DENSITY"
    SET_PROP "$part" "ro.sf.init.lcd_density" "$TARGET_LCD_DENSITY"
    SET_PROP "$part" "ro.product.${part}.model" "SM-G973F"
    SET_PROP "$part" "ro.product.${part}.name" "beyond1ltexx"
    SET_PROP "$part" "ro.product.${part}.device" "beyond1lte"
done
SET_PROP "system" "ro.product.model" "SM-G973F"
SET_PROP "system" "ro.product.name" "beyond1ltexx"
SET_PROP "system" "ro.product.device" "beyond1lte"
SET_PROP "system" "ro.build.product" "beyond1lte"

ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/bin/prepare_param.sh"

DECODE_APK "system" "system/framework/framework.jar"
bash "$MODPATH/app-overrides/stage-helper.sh" "$MODPATH/app-overrides" "$APKTOOL_DIR/system/framework/framework.jar" || exit 1
DECODE_APK "system" "system/priv-app/SecSettings/SecSettings.apk"
python3 "$MODPATH/app-overrides/patch-resolution.py" "$APKTOOL_DIR/system/priv-app/SecSettings/SecSettings.apk/smali_classes3" || exit 1
python3 "$MODPATH/settings-native/prepare.py" "$MODPATH/settings-native" "$APKTOOL_DIR/system/priv-app/SecSettings/SecSettings.apk" || exit 1
python3 "$MODPATH/settings-native/patch_bixby.py" "$APKTOOL_DIR/system/priv-app/SecSettings/SecSettings.apk/smali_classes5" || exit 1
SOURCE_BUILD_ID="$(GET_PROP "$WORK_DIR/system/system/build.prop" "ro.build.version.incremental")"
[[ -z "$SOURCE_BUILD_ID" ]] && SOURCE_BUILD_ID="S721BXXSFEZJ1"
SET_PROP "system" "ro.onerom.version" "$ROM_VERSION"
SET_PROP "system" "ro.onerom.build" "OneROM Delta 9.0 ($TARGET_CODENAME) ($SOURCE_BUILD_ID)"
SET_PROP "system" "ro.onerom.codename" "Delta"
SET_PROP "system" "ro.onerom.device" "$TARGET_CODENAME"
SET_PROP "system" "ro.onerom.build_date" "$(date +%Y-%m-%d)"
SET_PROP "system" "ro.onerom.build.date" "$(date +%Y-%m-%d)"
SET_PROP "system" "ro.build.display.id" "OneROM Delta 9.0 ($TARGET_CODENAME) ($SOURCE_BUILD_ID)"
SET_PROP "product" "ro.build.display.id" "OneROM Delta 9.0 ($TARGET_CODENAME) ($SOURCE_BUILD_ID)"
SET_PROP "system" "fw.max_users" "4"
SET_PROP "system" "fw.show_multiuserui" "1"

# USB Debugging & ADB Configuration based on build mode (--debug vs default/--release)
if [[ "${DEBUG:-false}" == "true" ]]; then
    echo "  -> Configuring early ADB and USB debugging for debug build"
    SET_PROP "system" "ro.debuggable" "1"
    SET_PROP "system" "ro.adb.secure" "0"
    SET_PROP "system" "persist.service.adb.enable" "1"
    SET_PROP "system" "persist.service.debuggable" "1"
    SET_PROP "system" "persist.sys.usb.config" "mtp,adb"
    SET_PROP "vendor" "ro.debuggable" "1"
    SET_PROP "product" "ro.debuggable" "1"
else
    echo "  -> Configuring release build (USB debugging disabled by default)"
    SET_PROP "system" "ro.debuggable" "0"
    SET_PROP "system" "ro.adb.secure" "1"
    SET_PROP "system" "persist.service.adb.enable" "0"
    SET_PROP "system" "persist.service.debuggable" "0"
    SET_PROP "system" "persist.sys.usb.config" "mtp"
    SET_PROP "vendor" "ro.debuggable" "0"
    SET_PROP "product" "ro.debuggable" "0"
fi

for keylayout in Generic Generic_internal Vendor_0075_Product_0100 Vendor_04e8; do
    keylayout_path="$WORK_DIR/system/system/usr/keylayout/$keylayout.kl"
    [[ -f "$keylayout_path" ]] || continue
    if grep -qE '^[[:space:]]*key[[:space:]]+703[[:space:]]' "$keylayout_path"; then
        sed -Ei 's/^[[:space:]]*key[[:space:]]+703[[:space:]]+.*/key 703   USER   WAKE/' "$keylayout_path"
    else
        printf '\nkey 703   USER   WAKE\n' >> "$keylayout_path"
    fi
done

patchelf --set-rpath /system/lib64 "$WORK_DIR/system/system/lib64/libvkmanager.so" || exit 1

IFS=/ read -r legacy_model legacy_region legacy_build <<< "$TARGET_FIRMWARE"
legacy_source="$FW_DIR/${legacy_model}_${legacy_region}"
legacy_output="$(mktemp -d)"
bash "$MODPATH/legacy32/stage-runtime.sh" "$legacy_source/system/system" "$legacy_source/vendor" "$legacy_output" || exit 1
mkdir -p "$legacy_output/vendor/lib" "$legacy_output/vendor/bin/hw"
mv "$legacy_output/lib" "$legacy_output/vendor/lib/s10-runtime32"
mv "$legacy_output/bin/s10-linker32" "$legacy_output/vendor/bin/s10-linker32"
mv "$legacy_output/bin/android.hardware.audio.service" "$legacy_output/vendor/bin/hw/android.hardware.audio.service"
mv "$legacy_output/bin/s10-soundtrigger32" "$legacy_output/vendor/bin/hw/s10-soundtrigger32"
mv "$legacy_output/bin/s10-bluetooth-audio64" "$legacy_output/vendor/bin/hw/s10-bluetooth-audio64"
mv "$legacy_output/bin/android.hardware.media.omx@1.0-service" "$legacy_output/vendor/bin/hw/android.hardware.media.omx@1.0-service"
mv "$legacy_output/bin/vendor.samsung.hardware.camera.provider@4.0-service" "$legacy_output/vendor/bin/hw/vendor.samsung.hardware.camera.provider@4.0-service"
ADD_TO_WORK_DIR "$legacy_output" "vendor" "lib/s10-runtime32" 0 0 755 "u:object_r:vendor_file:s0"
for legacy_library in "$WORK_DIR/vendor/lib/s10-runtime32/"*; do
    SET_METADATA "vendor" "lib/s10-runtime32/${legacy_library##*/}" 0 0 644 "u:object_r:vendor_file:s0"
done
cp "$legacy_source/system/system/lib/libGLESv1_CM.so" "$WORK_DIR/vendor/lib/libGLESv1_CM.so" || exit 1
SET_METADATA "vendor" "lib/libGLESv1_CM.so" 0 0 644 "u:object_r:vendor_file:s0"
ADD_TO_WORK_DIR "$legacy_output" "vendor" "bin/s10-linker32" 0 2000 755 "u:object_r:system_linker_exec:s0"
ADD_TO_WORK_DIR "$legacy_output" "vendor" "bin/hw/android.hardware.audio.service" 0 2000 755 "u:object_r:hal_audio_default_exec:s0"
ADD_TO_WORK_DIR "$legacy_output" "vendor" "bin/hw/s10-soundtrigger32" 0 2000 755 "u:object_r:hal_audio_default_exec:s0"
ADD_TO_WORK_DIR "$legacy_output" "vendor" "bin/hw/s10-bluetooth-audio64" 0 2000 755 "u:object_r:hal_audio_default_exec:s0"
ADD_TO_WORK_DIR "$legacy_output" "vendor" "bin/hw/android.hardware.media.omx@1.0-service" 0 2000 755 "u:object_r:mediacodec_exec:s0"
ADD_TO_WORK_DIR "$legacy_output" "vendor" "bin/hw/vendor.samsung.hardware.camera.provider@4.0-service" 0 2000 755 "u:object_r:hal_camera_default_exec:s0"
ADD_TO_WORK_DIR "$MODPATH" "vendor" "etc/init/android.hardware.media.omx@1.0-service.rc" 0 0 644 "u:object_r:vendor_configs_file:s0"
if [[ -f "$WORK_DIR/vendor/etc/init/android.hardware.audio.service.rc" ]]; then
    if ! grep -q 'setenv LD_LIBRARY_PATH' "$WORK_DIR/vendor/etc/init/android.hardware.audio.service.rc"; then
        sed -i '/service vendor.audio-hal/a\    setenv LD_LIBRARY_PATH /vendor/lib/s10-runtime32:/vendor/lib:/vendor/lib/hw' \
            "$WORK_DIR/vendor/etc/init/android.hardware.audio.service.rc"
    fi
fi
for codec_library in "$WORK_DIR"/vendor/lib/omx/*.so "$WORK_DIR/vendor/lib/libstagefright_softomx_plugin.so" "$WORK_DIR"/vendor/lib/hw/camera.*.so "$WORK_DIR/vendor/lib/hw/gralloc.exynos9820.so" "$WORK_DIR"/vendor/lib/hw/*audio*.so "$WORK_DIR"/vendor/lib/hw/audio.*.so; do
    [[ -f "$codec_library" ]] || continue
    patchelf --set-rpath /vendor/lib/s10-runtime32 "$codec_library" || exit 1
done
rm -rf "$legacy_output"


# S10 Stock Wallpapers (Android 17 adapted)
if [[ -f "$MODPATH/wallpaper-res/wallpaper-res.apk" ]]; then
    mkdir -p "$WORK_DIR/system/system/priv-app/wallpaper-res"
    cp -f "$MODPATH/wallpaper-res/wallpaper-res.apk" "$WORK_DIR/system/system/priv-app/wallpaper-res/wallpaper-res.apk"
    SET_METADATA "system" "system/priv-app/wallpaper-res/wallpaper-res.apk" 0 0 644 "u:object_r:system_file:s0"
fi

# S10 Lockscreen / Now Bar / Keyguard indication dimensions
for rro_dimens in "$APKTOOL_DIR"/product/overlay/SystemUI__*auto_generated_rro_product.apk/res/values/dimens.xml; do
    [[ -f "$rro_dimens" ]] || continue
    sed -i '/<\/resources>/d' "$rro_dimens"
    cat >> "$rro_dimens" << 'EOF'
    <dimen name="now_bar_bottom_margin">96.0dip</dimen>
    <dimen name="keyguard_indication_margin_bottom">152.0dip</dimen>
    <dimen name="keyguard_indication_margin_bottom_fingerprint_low_with_nowbar">152.0dip</dimen>
</resources>
EOF
done

IFS=/ read -r sdhms_model sdhms_region sdhms_build <<< "$SOURCE_FIRMWARE"
sdhms_output="$(mktemp -d)"
python3 "$MODPATH/sdhms/prepare-policies.py" \
    "$WORK_DIR/system/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk" \
    "$FW_DIR/${sdhms_model}_${sdhms_region}/system/system/etc/floating_feature.xml" \
    "$(GET_FLOATING_FEATURE_CONFIG "SEC_FLOATING_FEATURE_SYSTEM_CONFIG_SIOP_POLICY_FILENAME")" \
    "$SRC_DIR/target/$TARGET_CODENAME/dvfs/siop_model.xml" \
    "$sdhms_output/system/system/etc/s10-sdhms" || exit 1
ADD_TO_WORK_DIR "$sdhms_output" "system" "system/etc/s10-sdhms" 0 0 755 "u:object_r:system_file:s0"
for sdhms_policy in "$WORK_DIR/system/system/etc/s10-sdhms/"*; do
    SET_METADATA "system" "system/etc/s10-sdhms/${sdhms_policy##*/}" 0 0 644 "u:object_r:system_file:s0"
done
rm -rf "$sdhms_output"

# Android 17 libui dropped gralloc2; the S10 Mali vendor only provides mapper 2.1
ADD_TO_WORK_DIR "$MODPATH/gralloc2" "system" "system/lib64/libui.so" 0 0 644 "u:object_r:system_lib_file:s0"
ADD_TO_WORK_DIR "$MODPATH/gralloc2" "system" "system/lib64/libui_shim.so" 0 0 644 "u:object_r:system_lib_file:s0"

# Fix FORTIFY buffer overflow crash in ACodec::reconfigEncoder4OtherApps (fread 512 bytes into 255-byte buffer)
STAGEFRIGHT_PATH="$WORK_DIR/system/system/lib64/libstagefright.so"
if [[ -f "$STAGEFRIGHT_PATH" ]]; then
    stagefright_off="0x$(nm -D "$STAGEFRIGHT_PATH" | grep 'reconfigEncoder4OtherApps' | awk '{print $1}')"
    if [[ "$stagefright_off" != "0x" ]]; then
        python3 -c "import sys; f=open(sys.argv[1], 'r+b'); f.seek(int(sys.argv[2], 16)); f.write(bytes.fromhex('00008052c0035fd6'))" "$STAGEFRIGHT_PATH" "$stagefright_off" || exit 1
    fi
fi
# Shader-cache priming allocates a render target gralloc2 rejects, aborting SurfaceFlinger
SET_PROP "vendor" "service.sf.prime_shader_cache" "0"

if ! grep -qxF '/dev/ion u:object_r:ion_device:s0' "$WORK_DIR/system/system/etc/selinux/plat_file_contexts"; then
    printf '\n/dev/ion u:object_r:ion_device:s0\n' >> "$WORK_DIR/system/system/etc/selinux/plat_file_contexts"
fi

if ! grep -qF 'mount tmpfs tmpfs /metadata' "$WORK_DIR/system/system/etc/init/hw/init.rc"; then
    sed -i '/^on early-init$/a\    mkdir /metadata 0755 root root\n    mount tmpfs tmpfs /metadata mode=0755,uid=0,gid=0\n    restorecon_recursive /metadata' \
        "$WORK_DIR/system/system/etc/init/hw/init.rc"
fi

if ! grep -qxF 'import /vendor/ueventd.rc' "$WORK_DIR/system/system/etc/ueventd.rc"; then
	printf '\nimport /vendor/ueventd.rc\n' >> "$WORK_DIR/system/system/etc/ueventd.rc"
fi

sed -i '/^[[:space:]]*wait_for_prop bpf\.progs_loaded 1[[:space:]]*$/d' \
    "$WORK_DIR/system/system/etc/init/netbpfload.rc"

# Tethering netbpfload refuses the 5.4-reporting kernel (25Q4 needs 5.10); run a gate-patched copy from /system
NBL_TMP="$(mktemp -d)"
unzip -p "$WORK_DIR/system/system/apex/com.google.android.tethering_compressed.apex" original_apex > "$NBL_TMP/original.apex" || exit 1
unzip -p "$NBL_TMP/original.apex" apex_payload.img > "$NBL_TMP/payload.img" || exit 1
7z e -y "$NBL_TMP/payload.img" bin/netbpfload -o"$NBL_TMP" > /dev/null || exit 1
python3 - "$NBL_TMP/netbpfload" "$WORK_DIR/system/system/bin/netbpfload_s10" <<'EOF' || exit 1
import struct, sys
data = bytearray(open(sys.argv[1], "rb").read())
def words(*w): return struct.pack("<%dI" % len(w), *w)
patches = [
    # 25Q4 requires 5.10: tbz w10, #0 -> b past the error
    (words(0x3944914a, 0x360000ca, 0xb0ffffc1), words(0x3944914a, 0x14000006, 0xb0ffffc1)),
    # 26Q3 requires 5.15: tbz w8, #0 -> b past the error
    (words(0x3944a108, 0x36000128, 0xb0ffffc1), words(0x3944a108, 0x14000009, 0xb0ffffc1)),
    # BPF objects stay in the APEX; drop the object-vs-executable same-device check
    (words(0xeb05009f, 0x54002141, 0xf9401be1), words(0xeb05009f, 0xd503201f, 0xf9401be1)),
]
for old, new in patches:
    if data.count(old) != 1:
        sys.exit("netbpfload gate not found exactly once: " + old.hex())
    i = data.find(old)
    data[i:i + len(old)] = new
open(sys.argv[2], "wb").write(data)
EOF
7z x -y "$NBL_TMP/payload.img" 'javalib/*' -o"$NBL_TMP" > /dev/null || exit 1
baksmali d -a 34 --ac false --di false -l -j 4 -o "$NBL_TMP/smali" "$NBL_TMP/javalib/service-connectivity.jar" || exit 1
for connectivity_patch in "$MODPATH/connectivity/"*.patch; do
    git apply --unsafe-paths --directory="$NBL_TMP/smali" "$connectivity_patch" || exit 1
done
smali a -a 34 -j 4 -o "$NBL_TMP/classes.dex" "$NBL_TMP/smali" || exit 1
zip -q -j "$NBL_TMP/javalib/service-connectivity.jar" "$NBL_TMP/classes.dex" || exit 1
mkdir -p "$NBL_TMP/system/framework"
mv "$NBL_TMP/javalib" "$NBL_TMP/system/framework/s10-connectivity-javalib"
ADD_TO_WORK_DIR "$NBL_TMP" "system" "system/framework/s10-connectivity-javalib" 0 0 755 "u:object_r:system_file:s0"
for connectivity_file in "$WORK_DIR/system/system/framework/s10-connectivity-javalib/"*; do
    SET_METADATA "system" "system/framework/s10-connectivity-javalib/${connectivity_file##*/}" 0 0 644 "u:object_r:system_file:s0"
done
rm -rf "$NBL_TMP"
SET_METADATA "system" "system/bin/netbpfload_s10" 0 2000 750 "u:object_r:bpfloader_exec:s0"
if ! grep -q '^service bpfloader_s10 ' "$WORK_DIR/system/system/etc/init/netbpfload.rc"; then
    sed -i 's/^\([[:space:]]*\)exec_start bpfloader$/\1exec_start bpfloader_s10/' "$WORK_DIR/system/system/etc/init/netbpfload.rc"
    cat >> "$WORK_DIR/system/system/etc/init/netbpfload.rc" <<'EOF'

service bpfloader_s10 /system/bin/netbpfload_s10
    disabled
    capabilities CHOWN SYS_ADMIN NET_ADMIN SYSLOG
    group root graphics network_stack net_admin net_bw_acct net_bw_stats net_raw system
    user root
    file /dev/kmsg w
    rlimit memlock 1073741824 1073741824
    oneshot
EOF
fi

# 4.14 lacks Android 17 netd BPF support; skip libnetd_updatable_init and tolerate BandwidthController failure
python3 - "$WORK_DIR/system/system/bin/netd" <<'EOF' || exit 1
import struct, sys
path = sys.argv[1]
data = bytearray(open(path, "rb").read())
def words(*w): return struct.pack("<%dI" % len(w), *w)
NOP, MOV_W0_WZR, RET = 0xd503201f, 0x2a1f03e0, 0xd65f03c0
patches = [
    # main: bl libnetd_updatable_init; cbnz w0, fail
    (words(0x940193fa, 0x35000320), words(MOV_W0_WZR, 0x35000320)),
    # oneshot main: tail call libnetd_updatable_init(cgroup path) -> return 0
    (words(0x90fffbe0, 0x91133400, 0x910bc3ff, 0xa9434ff4, 0xf9400bfc, 0xa94257f6, 0xa8c47bfd, 0xd50323bf, 0x14019424),
     words(MOV_W0_WZR, NOP, 0x910bc3ff, 0xa9434ff4, 0xf9400bfc, 0xa94257f6, 0xa8c47bfd, 0xd50323bf, RET)),
    # Controllers::init: cbnz w0, "Failed to initialize BandwidthController" exit(2)
    (words(0x97ffc5c2, 0x35003aa0, 0x940130f2), words(0x97ffc5c2, NOP, 0x940130f2)),
]
for old, new in patches:
    if data.count(new) == 1 and data.count(old) == 0:
        continue
    if data.count(old) != 1:
        sys.exit("netd patch site not found exactly once: " + old.hex())
    i = data.find(old)
    data[i:i + len(old)] = new
open(path, "wb").write(data)
EOF

DELETE_FROM_WORK_DIR "system" "system/bin/fabric_crypto"
DELETE_FROM_WORK_DIR "system" "system/etc/init/fabric_crypto.rc"
DELETE_FROM_WORK_DIR "system" "system/etc/vintf/manifest/fabric_crypto_manifest.xml"
DELETE_FROM_WORK_DIR "system" "system/lib64/vendor.samsung.hardware.security.fkeymaster-V1-cpp.so"
DELETE_FROM_WORK_DIR "system" "system/lib64/vendor.samsung.hardware.security.fkeymaster-V1-ndk.so"