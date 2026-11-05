from pathlib import Path
import tempfile
import unittest
from integration.corerune import adapt, apply


def code(reg='v0', opcode='const-string/jumbo'):
    return f'''.class public Lcom/samsung/android/rune/CoreRune;
.super Ljava/lang/Object;
.method static constructor <clinit>()V
.locals 8
{opcode} {reg}, "ro.product.device"
invoke-static {{{reg}}}, Landroid/os/SystemProperties;->get(Ljava/lang/String;)Ljava/lang/String;
move-result-object {reg}
{opcode} {reg}, "ro.product.model"
invoke-static {{{reg}}}, Landroid/os/SystemProperties;->get(Ljava/lang/String;)Ljava/lang/String;
move-result-object {reg}
return-void
.end method
'''


class CoreTests(unittest.TestCase):
    def test_both_changes_preserve_other_instructions_and_are_idempotent(self):
        for reg, opcode in [('v0', 'const-string/jumbo'), ('v7', 'const-string')]:
            text = code(reg, opcode)
            expected = text.replace('ro.product.device', 'ro.product.vendor.device').replace('ro.product.model', 'ro.product.vendor.model')
            self.assertEqual(adapt(text), expected)
            self.assertEqual(adapt(expected), expected)

    def test_ambiguous_or_missing_reads_fail_without_partial_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'smali_classes8/com/samsung/android/rune/CoreRune.smali'
            path.parent.mkdir(parents=True)
            original = code().replace('ro.product.model', 'unrelated')
            path.write_text(original)
            with self.assertRaises(ValueError):
                apply(root)
            self.assertEqual(path.read_text(), original)
            with self.assertRaises(ValueError):
                adapt(code() + code())

    def test_settings_model_property_only_preserves_other_code(self):
        descriptor = 'Lcom/samsung/android/settings/deviceinfo/aboutphone/ModelNameGetter;'
        text = code('v7', 'const-string').replace('Lcom/samsung/android/rune/CoreRune;', descriptor)
        result = adapt(text, descriptor, [('ro.product.model', 'ro.boot.em.model')])
        self.assertEqual(result, text.replace('"ro.product.model"', '"ro.boot.em.model"'))
        self.assertEqual(adapt(result, descriptor, [('ro.product.model', 'ro.boot.em.model')]), result)

    def test_dex_relocation_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'smali_classes8/com/samsung/android/rune/CoreRune.smali'
            path.parent.mkdir(parents=True)
            path.write_text(code('v4', 'const-string'))
            apply(root)
            self.assertEqual(path.read_text().count('ro.product.vendor.'), 2)
