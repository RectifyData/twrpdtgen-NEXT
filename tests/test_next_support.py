# SPDX-License-Identifier: Apache-2.0
import tempfile
import unittest
from pathlib import Path

from twrpdtgen.next_support import (
    NextOptions, choose_recovery_layout, detect_android_api,
    normalize_partition_names, parse_partition_size, resolve_skeleton,
    safe_component, valid_security_patch,
)


class NextSupportTests(unittest.TestCase):
    def test_auto_skeleton_sdk(self):
        self.assertEqual(resolve_skeleton("auto", 34), "twrp-14.1")
        self.assertEqual(resolve_skeleton("auto", 36), "twrp-14.1")
        self.assertEqual(resolve_skeleton("auto", 33), "twrp-12.1")
        self.assertEqual(resolve_skeleton("auto", 30), "omni")
        self.assertEqual(resolve_skeleton("auto", None), "omni")
        self.assertEqual(resolve_skeleton("twrp-12.1", None), "twrp-12.1")

    def test_detect_api(self):
        with tempfile.TemporaryDirectory() as temp:
            prop = Path(temp) / "prop.default"
            prop.write_text("ro.build.version.sdk=35\n")
            self.assertEqual(detect_android_api(Path(temp)), 35)

    def test_partition_geometry(self):
        self.assertEqual(parse_partition_size("0x4000000"), 67108864)
        with self.assertRaises(ValueError):
            parse_partition_size("9126805503")
        with self.assertRaises(ValueError):
            NextOptions(super_size=4096, dynamic_group_size=4096)
        with self.assertRaises(ValueError):
            NextOptions(super_size=-4096)

    def test_unsafe_output_names(self):
        for bad in ("../escape", "..", "/tmp/out", "dev/name", ""):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                safe_component(bad)
        self.assertEqual(safe_component("beyond2lte"), "beyond2lte")

    def test_unique_partitions(self):
        self.assertEqual(normalize_partition_names(
            ["system", "vendor", "system", "/dev/block/system", None, "vendor_dlkm"]),
            ["system", "vendor", "vendor_dlkm"])

    def test_layout_never_equates_ab_with_recovery_as_boot(self):
        self.assertEqual(choose_recovery_layout("auto", "recovery.img", True), "dedicated")
        self.assertEqual(choose_recovery_layout("auto", "boot.img", True), "boot")
        self.assertEqual(choose_recovery_layout("auto", "unknown.img", True), "unknown")
        self.assertEqual(choose_recovery_layout("vendor_boot", "boot.img", False), "vendor_boot")

    def test_security_patch(self):
        self.assertEqual(valid_security_patch("2026-08-05"), "2026-08-05")
        self.assertIsNone(valid_security_patch("2099-12-31 unknown"))


if __name__ == "__main__":
    unittest.main()
