# SPDX-License-Identifier: Apache-2.0
import gzip
import tempfile
import unittest
from types import SimpleNamespace as Obj
from pathlib import Path

from twrpdtgen.next_support import (
    NextOptions, choose_recovery_layout, detect_android_api,
    detect_brightness_policy, detect_kernel_image_name,
    find_recovery_fstab, format_twrp_fstab,
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

    def test_split_ramdisk_metadata_search(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            generic = root / "generic"
            vendor = root / "vendor-root"
            generic.mkdir()
            vendor.mkdir()
            (generic / "prop.default").write_text(
                "ro.build.version.sdk=35\n")
            (vendor / "etc").mkdir()
            expected = vendor / "etc/recovery.fstab"
            expected.write_text("# split fstab\n")
            self.assertEqual(
                detect_android_api([generic, vendor]), 35)
            self.assertEqual(
                find_recovery_fstab([vendor, generic]), expected)

    def test_first_stage_fstab(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "first_stage_ramdisk").mkdir()
            candidate = root / "first_stage_ramdisk/fstab.qcom"
            candidate.write_text("# stock fstab\n")
            self.assertEqual(find_recovery_fstab(root), candidate)
            (root / "etc").mkdir()
            preferred = root / "etc/recovery.fstab"
            preferred.write_text("# recovery fstab\n")
            self.assertEqual(find_recovery_fstab(root), preferred)

    def test_partition_geometry(self):
        self.assertEqual(parse_partition_size("0x4000000"), 67108864)
        self.assertEqual(parse_partition_size("67108864"), 67108864)
        self.assertEqual(parse_partition_size("64MiB"), 67108864)
        self.assertEqual(parse_partition_size("64 mib"), 67108864)
        self.assertEqual(parse_partition_size("1GiB"), 1073741824)
        with self.assertRaises(ValueError):
            parse_partition_size("9126805503")
        with self.assertRaises(ValueError):
            parse_partition_size("64MB")
        with self.assertRaises(ValueError):
            parse_partition_size("nope")
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
        self.assertEqual(choose_recovery_layout("auto", "init_boot.img", False), "init_boot")
        self.assertEqual(choose_recovery_layout("auto", "init_boot_b.img", True), "init_boot")
        self.assertEqual(choose_recovery_layout("auto", "recovery_a.img", True), "dedicated")
        self.assertEqual(choose_recovery_layout("auto", "boot_b.img", True), "boot")
        self.assertEqual(NextOptions(recovery_layout="init_boot").recovery_layout,
                         "init_boot")

    def test_detect_brightness_policy_from_stock_init(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init = root / "init.recovery.qcom.rc"
            init.write_text(
                "on init\n"
                "    write /sys/class/backlight/panel0-backlight/brightness 200\n"
                "on shutdown\n"
                "    write /sys/class/backlight/panel0-backlight/brightness 0\n"
            )
            self.assertEqual(
                detect_brightness_policy(root),
                ("/sys/class/backlight/panel0-backlight/brightness", 200),
            )

            init.write_text(
                "on init\n"
                "    write /sys/class/backlight/panel0-backlight/brightness 180\n"
                "on boot\n"
                "    write /sys/class/backlight/panel0-backlight/brightness 200\n"
            )
            self.assertEqual(
                detect_brightness_policy(root),
                ("/sys/class/backlight/panel0-backlight/brightness", None),
            )

            nested = root / "vendor/etc/init"
            nested.mkdir(parents=True)
            (nested / "display.rc").write_text(
                "on boot\n"
                "    write /sys/class/leds/lcd-backlight/brightness 150\n"
            )
            self.assertEqual(
                detect_brightness_policy(root),
                (None, None),
            )

            # Notification LEDs must never be mistaken for the display.
            for child in nested.iterdir():
                child.unlink()
            init.write_text(
                "on init\n"
                "    write /sys/class/leds/red/brightness 255\n"
            )
            self.assertEqual(
                detect_brightness_policy(root),
                (None, None),
            )

            # Known LCD-backlight class paths are accepted.
            init.write_text(
                "on boot\n"
                "    write /sys/class/leds/lcd-backlight/brightness 150\n"
            )
            self.assertEqual(
                detect_brightness_policy(root),
                ("/sys/class/leds/lcd-backlight/brightness", 150),
            )

    def test_detect_legacy_kernel_image_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.write_bytes(b"not-compressed")
            self.assertEqual(detect_kernel_image_name(raw), "Image")

            gz = root / "gzip"
            gz.write_bytes(gzip.compress(b"kernel"))
            self.assertEqual(detect_kernel_image_name(gz), "Image.gz")

            gz_dtb = root / "gzip-dtb"
            gz_dtb.write_bytes(
                gzip.compress(b"kernel")
                + b"\xd0\x0d\xfe\xed"
                + b"\x00" * 64
            )
            self.assertEqual(
                detect_kernel_image_name(gz_dtb),
                "Image.gz-dtb",
            )

    def test_twrp_fstab_preserves_length_and_sar_mount(self):
        fstab = Obj(entries=[
            Obj(
                mount_point="/",
                fs_type="ext4",
                src="/dev/block/by-name/system",
                fs_flags=["recoveryonly"],
            ),
            Obj(
                mount_point="/data",
                fs_type="ext4",
                src="/dev/block/by-name/userdata",
                fs_flags=["wait", "length=-16384"],
            ),
        ])
        rendered = format_twrp_fstab(
            fstab,
            system_as_root=True,
        )
        self.assertIn(
            '/system_root ext4 /dev/block/by-name/system '
            'flags=display="System"',
            rendered,
        )
        self.assertIn(
            '/data ext4 /dev/block/by-name/userdata '
            'flags=display="data";wait;length=-16384',
            rendered,
        )

    def test_security_patch(self):
        self.assertEqual(valid_security_patch("2026-08-05"), "2026-08-05")
        self.assertIsNone(valid_security_patch("2099-12-31 unknown"))
        self.assertIsNone(valid_security_patch("2026-99-77"))


if __name__ == "__main__":
    unittest.main()
