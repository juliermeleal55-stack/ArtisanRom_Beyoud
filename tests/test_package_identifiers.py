from pathlib import Path
import tempfile
import unittest
from integration.package_inputs import read_prop, capture, retire, identifier
from test_build_stages import fixture, firmware

ALIASES=('ro.product.system.device','ro.product.device')
FINGERPRINTS=('ro.system.build.fingerprint','ro.build.fingerprint')


class PackageIdentifierTests(unittest.TestCase):
    def resolve(self, contents):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'build.prop';path.write_text(contents)
            return read_prop(path,'ro.build.product',ALIASES,FINGERPRINTS)

    def test_partition_scoped_and_generic_properties(self):
        for key in ('ro.build.product',*ALIASES):
            with self.subTest(key=key):
                self.assertEqual(self.resolve(f'{key}=e2s\n'),'e2s')
        self.assertEqual(self.resolve('ro.build.product=legacy\nro.product.system.device=modern\n'),'legacy')

    def test_fingerprint_fallback_extracts_device_not_product_or_model(self):
        for key in FINGERPRINTS:
            self.assertEqual(self.resolve(f'{key}=samsung/e2sxxx/e2s:16/BP2A.250605.031.A3/S926BXXSIEZJ1:user/release-keys\n'),'e2s')

    def test_invalid_or_duplicate_preferred_property_is_never_masked(self):
        for value in ('ro.build.product=\n','ro.build.product=bad/value\n','ro.build.product=e2s\nro.build.product=e2s\n'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.resolve(value+'ro.product.system.device=e2s\n')
        for contents in ('ro.product.model=SM-S926B\n','ro.system.build.fingerprint=bad\n',
                         'ro.system.build.fingerprint=samsung/e2sxxx/../escape:16/id/build:user/release-keys\n'):
            with self.subTest(contents=contents),self.assertRaises(ValueError):self.resolve(contents)

    def test_modern_donor_identifiers_survive_firmware_retirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root);firmware(root)
            prop=root/'out/fw/SM-S926B_EUX/system/system/build.prop'
            prop.write_text('ro.product.system.device=e2s\nro.build.version.sdk=37\n')
            self.assertEqual(capture(root)['identifiers']['source_product'],'e2s')
            retire(root)
            self.assertFalse((root/'out/fw').exists())
            self.assertEqual(identifier(root,'source_product'),'e2s')
            self.assertEqual(identifier(root,'source_vendor'),'e2sxx')

    def test_bad_identifier_does_not_delete_firmware(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root);firmware(root)
            prop=root/'out/fw/SM-S926B_EUX/system/system/build.prop'
            prop.write_text('ro.product.model=SM-S926B\n')
            with self.assertRaises(ValueError):retire(root)
            self.assertTrue(prop.exists())
            self.assertFalse((root/'out/beyoud-fw-retired.json').exists())

    def test_workflow_checks_identifiers_before_expensive_patch_stage(self):
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/alpha.yml').read_text()
        self.assertLess(workflow.index('package_inputs.py" verify'),workflow.index('build_candidate.sh "$WORKSPACE" patch'))
