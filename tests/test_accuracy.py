# SPDX-License-Identifier: Apache-2.0
"""Source-evidence checks for TWRP tree accuracy."""
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from twrpdtgen.next_support import (
    detect_stock_filesystem_types, valid_security_patch,
)


class SourceEvidenceTests(unittest.TestCase):
    def parse(self, contents):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "recovery.fstab"
            file.write_text(contents, encoding="utf-8")
            return detect_stock_filesystem_types(file)

    def test_android_stock_fs_mgr_fstab_uses_actual_types(self):
        found = self.parse(
            "/dev/block/by-name/system /system ext4 ro wait\n"
            "/dev/block/by-name/vendor /vendor erofs ro wait\n"
            "/dev/block/by-name/userdata /data f2fs rw wait,check,encryptable\n"
        )
        self.assertEqual(found, {
            "system": "ext4", "vendor": "erofs", "userdata": "f2fs",
        })

    def test_twrp_recovery_style_entries(self):
        found = self.parse(
            "/system_root erofs /dev/block/mapper/system flags=logical\n"
            "/vendor ext4 /dev/block/mapper/vendor flags=logical\n"
            "/data f2fs /dev/block/by-name/userdata flags=encryptable\n"
        )
        self.assertEqual(found, {
            "system": "erofs", "vendor": "ext4", "userdata": "f2fs",
        })

    def test_conflicting_and_unsupported_types_are_not_assumed(self):
        found = self.parse(
            "/dev/block/by-name/system /system ext4 ro wait\n"
            "/dev/block/by-name/system /system erofs ro wait\n"
            "/dev/block/by-name/vendor /vendor squashfs ro wait\n"
            "/dev/block/by-name/userdata /data f2fs rw wait\n"
        )
        self.assertEqual(found, {"userdata": "f2fs"})

    def test_do_not_infer_from_wrong_mount_or_type(self):
        found = self.parse(
            "# /data ext4 /dev/block/invalid\n"
            "/dev/block/foo /metadata ext4 rw wait\n"
            "/dev/block/foo /data unknown rw wait\n"
            "system ext4 /dev/block/system\n"
            "/dev/block/foo /data f2fs rw wait # comment\n"
        )
        self.assertEqual(found, {"userdata": "f2fs"})

    def test_security_patch_cannot_be_future_placeholder(self):
        self.assertIsNone(valid_security_patch("2099-12-31"))
        self.assertIsNone(valid_security_patch("2038-01-01"))
        self.assertIsNone(valid_security_patch("2010-01-01"))
        self.assertIsNone(valid_security_patch("2026-02-30"))
        self.assertIsNone(valid_security_patch("not a date"))
        today = date.today().strftime("%Y-%m-%d")
        self.assertEqual(valid_security_patch(today), today)
        too_far = (date.today() + timedelta(days=46)).strftime("%Y-%m-%d")
        self.assertIsNone(valid_security_patch(too_far))


if __name__ == "__main__":
    unittest.main()
