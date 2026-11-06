import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from integration.smali_paths import resolve, resolve_apk_path
from integration.smali_patch import apply
from integration.semantic_smali import method_return, force_applock
from integration.overlay_resources import prune
from integration.runtime_paths import install

ROOT=Path(__file__).resolve().parents[1]


def write_class(root,path,body):
    file=root/path;file.parent.mkdir(parents=True,exist_ok=True)
    descriptor='L'+path.split('/',1)[1][:-6]+';'
    file.write_text('.class public '+descriptor+'\n.super Ljava/lang/Object;\n'+body)
    return file


class SmaliAdaptationsTests(unittest.TestCase):
    def test_exact_package_descriptor_relocation_not_basename(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            expected=write_class(root,'smali_classes8/p/A.smali','')
            write_class(root,'smali_classes2/other/A.smali','')
            self.assertEqual(resolve(root,'smali_classes4/p/A.smali'),expected)
            write_class(root,'smali/p/A.smali','')
            with self.assertRaises(ValueError):resolve(root,'smali_classes4/p/A.smali')

    def test_wrong_descriptor_and_escaping_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            file=write_class(root,'smali/p/A.smali','')
            file.write_text('.class public Lother/A;\n')
            with self.assertRaises(ValueError):resolve(root,'smali/p/A.smali')
            file.unlink();file.symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):resolve(root,'smali/p/A.smali')
            with self.assertRaises(ValueError):resolve(root,'../A.smali')

    def test_relocated_patch_keeps_strict_hunks_and_original_patch(self):
        with tempfile.TemporaryDirectory() as t:
            workspace=Path(t);decoded=workspace/'decoded';decoded.mkdir()
            file=write_class(decoded,'smali_classes8/p/A.smali','old\n')
            patch=workspace/'test.patch'
            raw='diff --git a/smali_classes4/p/A.smali b/smali_classes4/p/A.smali\n--- a/smali_classes4/p/A.smali\n+++ b/smali_classes4/p/A.smali\n@@ -3 +3 @@\n-old\n+new\n'
            patch.write_text(raw)
            result,_=apply(workspace,decoded,patch)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(file.read_text().endswith('new\n'))
            self.assertEqual(patch.read_text(),raw)
            before=file.read_bytes()
            result,_=apply(workspace,decoded,patch)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(file.read_bytes(),before)

    def test_pinned_version_equivalent_is_atomic_across_both_classes(self):
        name='unica/mods/deknox/smali/system/framework/knoxsdk.jar/0001-Nuke-Knox-DualDAR-and-HDM-version.patch'
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);decoded=root/'decoded';decoded.mkdir()
            patch=root/name;patch.parent.mkdir(parents=True);shutil.copyfile(ROOT/'reference/build'/name,patch)
            original='.method public static greylist getDualDARVersion()Ljava/lang/String;\n.locals 1\nconst-string v0, "1.9.0"\nreturn-object v0\n.end method\n'
            ddar=write_class(decoded,'smali_classes9/com/samsung/android/knox/ddar/DualDARPolicy.smali',original)
            before=ddar.read_bytes()
            result,_=apply(root,decoded,patch)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(ddar.read_bytes(),before)
            hdm=write_class(decoded,'smali_classes7/com/samsung/android/knox/hdm/HdmManager.smali','.method public static greylist getHdmVersion()Ljava/lang/String;\n.locals 1\nconst-string v0, "ro.vendor.hdm.version.tlc"\nreturn-object v0\n.end method\n')
            result,_=apply(root,decoded,patch)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('const/4 v0, 0x0',ddar.read_text());self.assertIn('const/4 v0, 0x0',hdm.read_text())
            stable=ddar.read_text();result,_=apply(root,decoded,patch)
            self.assertEqual(result.returncode,0);self.assertEqual(ddar.read_text(),stable)
            patch.write_text(patch.read_text()+'\n')
            self.assertNotEqual(apply(root,decoded,patch)[0].returncode,0)

    def test_method_guards_preserve_other_methods_and_annotations(self):
        text='.method public static getHdmVersion()Ljava/lang/String;\n.locals 4\n.annotation runtime Lp/Marker;\n.end annotation\nconst-string v2, "2.1"\nreturn-object v2\n.end method\n.method public untouched()V\n.locals 0\nreturn-void\n.end method\n'
        changed=method_return(text,'getHdmVersion()Ljava/lang/String;','null',True)
        self.assertIn('untouched()V',changed);self.assertIn('.annotation runtime Lp/Marker;',changed)
        with self.assertRaises(ValueError):method_return(text,'getHdmVersion()Ljava/lang/String;','null',False)
        with self.assertRaises(ValueError):method_return(text+text,'getHdmVersion()Ljava/lang/String;','null',True)

    def test_applock_does_not_overwrite_live_donor_register(self):
        text='.method static constructor <clinit>()V\n.locals 25\nconst/4 v15, 0x0\nsput-boolean v15, Lcom/samsung/android/rune/CoreRune;->FW_SUPPORT_APPLOCK:Z\nsput-boolean v15, Lcom/samsung/android/rune/CoreRune;->FW_APPLOCK:Z\nsput-boolean v15, Lp/Other;->KEEP_FALSE:Z\nreturn-void\n.end method\n'
        changed=force_applock(text)
        self.assertIn('.locals 26',changed)
        self.assertIn('const/16 v25, 0x1',changed)
        self.assertIn('sput-boolean v15, Lp/Other;->KEEP_FALSE:Z',changed)
        self.assertEqual(force_applock(changed),changed)

    def test_overlay_already_absent_is_ok_but_other_ids_are_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);values=root/'res/values';values.mkdir(parents=True)
            (values/'bools.xml').write_text('<resources><bool name="config_enableRoundedCorner">true</bool><bool name="keep">true</bool></resources>')
            (values/'public.xml').write_text('<resources><public type="bool" name="config_enableRoundedCorner" id="0x7f010001"/><public type="string" name="keep" id="0x7f020001"/></resources>')
            prune(root)
            self.assertEqual([e.get('name') for e in ET.parse(values/'bools.xml').getroot()],['keep'])
            self.assertEqual(ET.parse(values/'public.xml').getroot()[0].get('id'),'0x7f020001')
            before=(values/'public.xml').read_bytes();prune(root);self.assertEqual(before,(values/'public.xml').read_bytes())

    def test_runtime_installer_relocates_inline_paths_and_retains_native_checks(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);shutil.copytree(ROOT/'reference/build',root,dirs_exist_ok=True)
            install(root)
            for p in root.rglob('*.sh'):subprocess.run(['bash','-n',str(p)],check=True)
            product=(root/'unica/patches/product_feature/customize.sh').read_text()
            self.assertIn('smali_paths.py',product)
            camera=(root/'platform/exynos9820/patches/camera/customize.sh').read_text()
            self.assertIn('82fbffb042301f91c000805213f30594e0031a2a47feff17',camera)
            self.assertIn('HEX_PATCH',camera)
            self.assertNotIn('wait $(jobs -p)',camera)
            self.assertIn('overlay_resources.py',(root/'unica/patches/rro/customize.sh').read_text())

    def test_replay_requires_exact_retained_hash_and_never_calls_firmware_tools(self):
        from scripts.replay_patch_diagnostics import replay
        import hashlib
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            body='.method static constructor <clinit>()V\n.locals 16\nconst/4 v15, 0x0\nsput-boolean v15, Lcom/samsung/android/rune/CoreRune;->FW_SUPPORT_APPLOCK:Z\nsput-boolean v15, Lcom/samsung/android/rune/CoreRune;->FW_APPLOCK:Z\nreturn-void\n.end method\n'
            source=write_class(root,'smali_classes9/com/samsung/android/rune/CoreRune.smali',body)
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            event=dict(kind='patch',status='failed',patch='unica/mods/applock/smali/system/framework/framework.jar/0001-Force-AppLock-support.patch',inputs={'out/target/beyond1lte/apktool/system/framework/framework.jar/smali_classes9/com/samsung/android/rune/CoreRune.smali':digest})
            report=root/'patch-preflight.json';report.write_text(json.dumps(dict(events=[event])))
            with contextlib.redirect_stdout(io.StringIO()):result=replay(root)
            self.assertEqual(result[0]['status'],'passed')
            source.write_text(source.read_text()+'\n')
            with contextlib.redirect_stdout(io.StringIO()):result=replay(root)
            self.assertEqual(result[0]['status'],'unavailable')

    def test_native_capture_does_not_change_or_approve_incompatible_binary(self):
        from integration.native_patch_input import capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);file=root/'out/target/beyond1lte/work_dir/system/system/lib64/libstagefright.so'
            file.parent.mkdir(parents=True);file.write_bytes(b'actual incompatible input')
            capture(root,file,'1234','5678')
            self.assertEqual(file.read_bytes(),b'actual incompatible input')
            reports=list((root/'out/beyoud-logs/native-inputs').glob('*.json'))
            self.assertEqual(len(reports),1)
            self.assertEqual(json.loads(reports[0].read_text())['status'],'input-only-native-fix-unvalidated')

    def test_hidden_api_initializer_modifier_is_accepted(self):
        text='.method static constructor blacklist <clinit>()V\n.locals 25\nconst/4 v15, 0x0\nsput-boolean v15, Lcom/samsung/android/rune/CoreRune;->FW_SUPPORT_APPLOCK:Z\nsput-boolean v15, Lcom/samsung/android/rune/CoreRune;->FW_APPLOCK:Z\nreturn-void\n.end method\n'
        self.assertIn('sput-boolean v25',force_applock(text))

    def test_telecom_absence_is_proven_only_for_the_legacy_target_behavior(self):
        text='.class public Lcom/samsung/server/telecom/device/bluetooth/SamsungBluetoothRouteManager;\n'
        signature='setCallEndTonePlayStatus(Z)V'
        self.assertEqual(method_return(text,signature,'void',False,True),text)
        with self.assertRaises(ValueError):method_return(text+'# setCallEndTonePlayStatus\n',signature,'void',False,True)
        with self.assertRaises(ValueError):method_return(text,'other()V','void',False,True)

    def test_hdm_rebase_is_strict_and_hash_pinned(self):
        name='unica/mods/deknox/smali/system/framework/services.jar/0005-Nuke-HDMService.patch'
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);decoded=root/'decoded';decoded.mkdir()
            patch=root/name;patch.parent.mkdir(parents=True);shutil.copyfile(ROOT/'reference/build'/name,patch)
            body='.method public init()V\n.locals 16\ninvoke-static {v0, v3}, Landroid/os/ServiceManager;->addService(Ljava/lang/String;Landroid/os/IBinder;)V\n\nconst-string/jumbo v3, "hdm_service"\n\nnew-instance v4, Lcom/android/server/enterprise/hdm/HdmService;\n\n'+'# inline initialization\n'*270+'invoke-static {v4, v3}, Lcom/android/server/enterprise/EnterpriseDeviceManagerServiceImpl$Injector;->addLazySystemService(Lcom/android/server/enterprise/EnterpriseServiceCallback;Ljava/lang/String;)V\n\niget-object v0, v1, Lcom/android/server/enterprise/EnterpriseDeviceManagerServiceImpl;->mContext:Landroid/content/Context;\n\nsget v2, Lcom/android/server/enterprise/appconfig/ApplicationRestrictionsService;->$r8$clinit:I\n\nreturn-void\n.end method\n'
            body=''.join(('    '+line if line.strip() and not line.startswith(('.', '#')) else line) for line in body.splitlines(keepends=True))
            file=write_class(decoded,'smali/com/android/server/enterprise/EnterpriseDeviceManagerServiceImpl.smali',body)
            result,_=apply(root,decoded,patch)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('goto/16 :s10_hdm_skipped',file.read_text())
            before=file.read_bytes();patch.write_text(patch.read_text()+'\n')
            self.assertNotEqual(apply(root,decoded,patch)[0].returncode,0)
            self.assertEqual(file.read_bytes(),before)

    def test_source_only_capture_does_not_request_target_patch_or_rom_stages(self):
        text=(ROOT/'.github/workflows/collect-donor-repair-inputs.yml').read_text()
        self.assertIn('build_candidate.sh "$WORKSPACE" source',text)
        for stage in ('target','patch','retire','package'):
            self.assertNotIn('build_candidate.sh "$WORKSPACE" '+stage,text)
        self.assertNotIn('collect_alpha.py',text)
        self.assertIn('not a ROM or installer',text)
