from pathlib import Path
import tempfile
import unittest
from integration.refresh_rate import adapt, apply
from integration.framework_policy import install, PRODUCT, HFR_PATCH
import shutil

CLASS = 'Lcom/samsung/android/hardware/display/RefreshRateConfig;'


def code(brt='89,91', lux='260,2500', regs=('v3','v4','v1','v2')):
    b,l,p,q = regs
    return f'''.class public {CLASS}
.super Ljava/lang/Object;
.method public dump()V
.locals 1
const-string v0, "SEAMLESS_BRT: {brt}"
const-string/jumbo v0, "SEAMLESS_LUX: {lux}"
return-void
.end method
.method public static blacklist getMainInstance(){CLASS}
.locals 12
new-instance v0, {CLASS[:-1]}$BrightnessThreshold;
const-string/jumbo {p}, "persist.dm.passive.display_brightness"
const-string/jumbo {q}, "persist.dm.passive.ambient_brightness"
const-string {b}, "{brt}"
const-string/jumbo {l}, "{lux}"
invoke-direct {{v0, {b}, {l}, {p}, {q}}}, {CLASS[:-1]}$BrightnessThreshold;-><init>(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V
return-object v0
.end method
.method public unrelated()V
.locals 1
const-string v0, "{brt}"
return-void
.end method
'''


class RefreshRateTests(unittest.TestCase):
    def test_old_and_changed_donor_thresholds_registers_opcodes(self):
        for brt, lux, regs in [('89,91','260,2500',('v3','v4','v1','v2')),
                               ('100,120','300,1500',('v7','v8','v5','v6'))]:
            original = code(brt,lux,regs)
            changed = adapt(original)
            self.assertIn('const-string '+regs[0]+', ""', changed)
            self.assertIn('const-string/jumbo '+regs[1]+', ""', changed)
            self.assertIn('"SEAMLESS_BRT: "', changed)
            self.assertIn('"SEAMLESS_LUX: "', changed)
            self.assertIn('const-string v0, "'+brt+'"', changed)
            self.assertIn('.locals 12', changed)
            self.assertEqual(adapt(changed), changed)

    def test_changed_dataflow_properties_or_ambiguous_constructor_block(self):
        original = code()
        call = next(l for l in original.splitlines() if 'invoke-direct' in l)
        variants = [original.replace('persist.dm.passive.ambient_brightness','unrelated'),
                    original.replace(call, call+'\n'+call),
                    original.replace(call,'move-object v3, v4\n'+call),
                    code('not-a-threshold'), original.replace('getMainInstance()', 'other()')]
        for text in variants:
            with self.subTest(text=text), self.assertRaises(ValueError):
                adapt(text)

    def test_dex_relocation_and_no_partial_write_on_bad_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / 'smali_classes9/com/samsung/android/hardware/display/RefreshRateConfig.smali'
            file.parent.mkdir(parents=True)
            original = code().replace('SEAMLESS_LUX: 260,2500','SEAMLESS_LUX: unknown')
            file.write_text(original)
            with self.assertRaises(ValueError):
                apply(root)
            self.assertEqual(file.read_text(),original)
            file.write_text(code('120,130','20,500'))
            apply(root)
            self.assertEqual(file.read_text(),adapt(code('120,130','20,500')))

    def test_installer_replaces_only_the_original_conditional_hfr_call(self):
        base = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(base/'reference/build',root,dirs_exist_ok=True)
            original = (root/PRODUCT).read_text()
            call = 'APPLY_PATCH "system" "system/framework/framework.jar" "$SRC_DIR/'+str(HFR_PATCH)+'"'
            replacement = 'python3 "$SRC_DIR/integration/refresh_rate.py" "$APKTOOL_DIR/system/framework/framework.jar" || exit 1'
            install(root)
            self.assertEqual((root/PRODUCT).read_text(), original.replace(call,replacement))
            self.assertFalse((root/HFR_PATCH).exists())
