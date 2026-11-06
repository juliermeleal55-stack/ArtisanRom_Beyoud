import unittest
from pathlib import Path

from integration.runtime_paths import rebase_camera_native_patches

ROOT = Path(__file__).resolve().parents[1]


class CameraNativeRebaseTests(unittest.TestCase):
    def test_pinned_camera_commands_are_rebased_to_s926b_layout(self):
        original = (ROOT / 'reference/build/platform/exynos9820/patches/camera/customize.sh').read_text()
        patched = rebase_camera_native_patches(original)
        self.assertIn(
            '"82fbffb042301f91c000805213f30594e0031a2a47feff17" '
            '"82fbffb042301f91c000805213f30594e0031a2a0e000014"',
            patched,
        )
        self.assertIn(
            '"010140f935f5059400470034" "010140f935f505941f2003d5"',
            patched,
        )
        self.assertNotIn('"da4a0594e0031a2a22feff17"', patched)
        self.assertNotIn('"010140f90a4d0594604d0034"', patched)

    def test_svc_branch_replacement_skips_only_the_error_return_block(self):
        branch = int.from_bytes(bytes.fromhex('0e000014'), 'little')
        immediate = branch & 0x03ffffff
        if immediate & (1 << 25):
            immediate -= 1 << 26
        self.assertEqual(0xec86c + (immediate << 2), 0xec8a4)

    def test_unexpected_reference_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'Video SVC'):
            rebase_camera_native_patches('no pinned camera commands here')


if __name__ == '__main__':
    unittest.main()
