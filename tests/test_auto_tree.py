# SPDX-License-Identifier: Apache-2.0
import tempfile
import unittest
from pathlib import Path

from twrpdtgen.auto_tree import discover_images


class AutoTreeDiscoveryTests(unittest.TestCase):
    def test_prefers_recovery_and_attaches_companions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in (
                "recovery.img",
                "boot.img",
                "vendor_boot.img",
                "init_boot.img",
            ):
                (root / name).write_bytes(b"x")

            images = discover_images(root)
            self.assertEqual(images.primary, root / "recovery.img")
            self.assertEqual(images.boot, root / "boot.img")
            self.assertEqual(
                images.vendor_boot,
                root / "vendor_boot.img",
            )
            self.assertEqual(
                images.init_boot,
                root / "init_boot.img",
            )

    def test_prefers_unsuffixed_then_slot_a_then_slot_b(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "boot_b.img").write_bytes(b"b")
            (root / "boot_a.img").write_bytes(b"a")
            images = discover_images(root)
            self.assertEqual(images.boot, root / "boot_a.img")

            (root / "boot.img").write_bytes(b"plain")
            images = discover_images(root)
            self.assertEqual(images.boot, root / "boot.img")

    def test_uses_vendor_boot_when_no_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "vendor_boot.img").write_bytes(b"vendor")
            (root / "boot.img").write_bytes(b"boot")
            images = discover_images(root)
            self.assertEqual(
                images.primary,
                root / "vendor_boot.img",
            )

    def test_nested_standard_images_are_discovered(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nested = root / "factory" / "images"
            nested.mkdir(parents=True)
            (nested / "recovery.img").write_bytes(b"recovery")
            images = discover_images(root)
            self.assertEqual(
                images.recovery,
                nested / "recovery.img",
            )

    def test_equal_rank_duplicates_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            one = root / "one"
            two = root / "two"
            one.mkdir()
            two.mkdir()
            (one / "boot.img").write_bytes(b"1")
            (two / "boot.img").write_bytes(b"2")
            with self.assertRaisesRegex(
                    ValueError, "Ambiguous boot.img"):
                discover_images(root)

    def test_missing_supported_image_is_clear(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "system.img").write_bytes(b"system")
            with self.assertRaisesRegex(
                    ValueError, "No supported Android image"):
                discover_images(root)


if __name__ == "__main__":
    unittest.main()
