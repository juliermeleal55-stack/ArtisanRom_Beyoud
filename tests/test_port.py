import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("port", Path(__file__).resolve().parents[1] / "scripts/port.py")
port = importlib.util.module_from_spec(spec)
spec.loader.exec_module(port)


class ReadinessTests(unittest.TestCase):
    def test_sources_are_pinned(self):
        self.assertEqual(len(port.load_manifest()["sources"]), 4)

    def test_empty_profile_is_blocked(self):
        self.assertEqual(len(port.doctor({})), len(port.CHECKS) + 1)

    def test_truthy_strings_do_not_approve(self):
        self.assertIn("hardware_confirmed", port.doctor({"hardware_confirmed": "true"}))

    def test_release_requires_all_checks(self):
        profile = dict.fromkeys(port.CHECKS, True)
        self.assertEqual(port.doctor(profile), ["release_validated"])
        profile.update(status="validated", flashable=True)
        self.assertEqual(port.doctor(profile), [])
        profile["boot_validated"] = False
        self.assertIn("boot_validated", port.doctor(profile))

    def test_evidence_cannot_overwrite_project(self):
        with self.assertRaises(ValueError):
            port.inspect(port.ROOT / "scratch")


if __name__ == "__main__":
    unittest.main()
