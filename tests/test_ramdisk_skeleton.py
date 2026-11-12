# SPDX-License-Identifier: Apache-2.0
import tempfile
import unittest
from pathlib import Path

from twrpdtgen.ramdisk_skeleton import (
    is_device_overlay_path,
    materialize_recovery_skeleton,
)


class RamdiskSkeletonTests(unittest.TestCase):
    def test_minimal_mode_filters_generic_recovery_program(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            (source / "system/bin").mkdir(parents=True)
            (source / "vendor/etc/init").mkdir(parents=True)
            (source / "system/bin/recovery").write_text("stock")
            (source / "init.rc").write_text("generic")
            (source / "init.recovery.qcom.rc").write_text("device")
            (source / "vendor/etc/init/hw.rc").write_text("vendor")
            report = materialize_recovery_skeleton(
                source,
                root / "stock",
                root / "build",
                "minimal")
            self.assertTrue((root / "stock/system/bin/recovery").is_file())
            self.assertFalse((root / "build/system/bin/recovery").exists())
            self.assertFalse((root / "build/init.rc").exists())
            self.assertTrue((root / "build/init.recovery.qcom.rc").is_file())
            self.assertTrue((root / "build/vendor/etc/init/hw.rc").is_file())
            self.assertEqual(report["mode"], "minimal")

    def test_full_mode_copies_typed_recovery_fragment_exactly(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            (source / "system/bin").mkdir(parents=True)
            (source / "system/bin/recovery").write_text("fragment")
            (source / "init.rc").write_text("fragment init")
            materialize_recovery_skeleton(
                source,
                root / "stock",
                root / "build",
                "full")
            self.assertEqual(
                (root / "build/system/bin/recovery").read_text(),
                "fragment")
            self.assertEqual(
                (root / "build/init.rc").read_text(),
                "fragment init")

    def test_overlay_selector(self):
        self.assertTrue(is_device_overlay_path("vendor/lib64/keymint.so"))
        self.assertTrue(is_device_overlay_path("init.recovery.mt6895.rc"))
        self.assertTrue(is_device_overlay_path("system/etc/vintf/manifest.xml"))
        self.assertFalse(is_device_overlay_path("system/bin/recovery"))
        self.assertFalse(is_device_overlay_path("init.rc"))


if __name__ == "__main__":
    unittest.main()
