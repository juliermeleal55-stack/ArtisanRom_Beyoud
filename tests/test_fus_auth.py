import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fus_check', ROOT / 'scripts/check_fus_auth.py')
fus_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fus_check)


class FusAuthTests(unittest.TestCase):
    def test_dependency_matches_unica_revision(self):
        data = json.loads((ROOT / 'manifests/artisan-submodules.json').read_text())
        entry = next(item for item in data if item['path'] == 'external/samloader')
        self.assertEqual(entry['url'], 'https://github.com/ananjaser1211/samloader.git')
        self.assertEqual(entry['commit'], '3c372007945d4f3f165433a1d5ae40523d7f68bf')

    def test_empty_nonce_is_rejected_before_signing(self):
        auth = Mock()
        auth.decryptnonce.return_value = ''
        with self.assertRaises(ValueError):
            fus_check.verify(auth)
        auth.getauth.assert_not_called()

    def test_bad_nonce_is_rejected(self):
        auth = Mock()
        auth.decryptnonce.return_value = 'invalid-nonce'
        with self.assertRaises(ValueError):
            fus_check.verify(auth)

    def test_empty_signature_is_rejected(self):
        auth = Mock()
        auth.decryptnonce.return_value = fus_check.PLAINTEXT_NONCE
        auth.getauth.return_value = ''
        with self.assertRaises(ValueError):
            fus_check.verify(auth)
