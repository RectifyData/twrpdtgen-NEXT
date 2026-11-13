# SPDX-License-Identifier: Apache-2.0
import tempfile
import unittest
from pathlib import Path
import zipfile

from twrpdtgen.easy import (
    EasyModeError,
    _clean_drag_drop_path,
    _safe_zip_images,
    _unique_path,
    prepared_input,
)


class EasyModeTests(unittest.TestCase):
    def test_drag_drop_quotes_are_removed(self):
        self.assertEqual(
            _clean_drag_drop_path('"C:\\Firmware Files\\recovery.img"'),
            "C:\\Firmware Files\\recovery.img",
        )
        self.assertEqual(
            _clean_drag_drop_path("'/tmp/recovery.img'"),
            "/tmp/recovery.img",
        )

    def test_unique_output_never_overwrites_previous_work(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "twrp-device-tree.zip"
            original.write_bytes(b"old")
            self.assertEqual(
                _unique_path(original),
                root / "twrp-device-tree-2.zip",
            )

    def test_zip_extracts_only_images_and_flattens_safe_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "firmware.zip"
            out = root / "out"
            out.mkdir()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("images/recovery.img", b"recovery")
                bundle.writestr("images/boot.img", b"boot")
                bundle.writestr("notes.txt", b"ignore")
                bundle.writestr("../escape.img", b"bad")
            count = _safe_zip_images(archive, out)
            self.assertEqual(count, 2)
            self.assertEqual((out / "recovery.img").read_bytes(), b"recovery")
            self.assertEqual((out / "boot.img").read_bytes(), b"boot")
            self.assertFalse((root / "escape.img").exists())

    def test_zip_without_images_has_clear_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "empty.zip"
            out = root / "out"
            out.mkdir()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("README.txt", b"nothing")
            with self.assertRaisesRegex(
                    EasyModeError, "contains no .img files"):
                _safe_zip_images(archive, out)

    def test_standard_single_image_auto_collects_companions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            recovery = root / "recovery.img"
            boot = root / "boot.img"
            recovery.write_bytes(b"recovery")
            boot.write_bytes(b"boot")
            with prepared_input(recovery) as (prepared, explicit):
                self.assertIsNone(explicit)
                self.assertTrue((prepared / "recovery.img").is_file())
                self.assertTrue((prepared / "boot.img").is_file())

    def test_arbitrary_single_image_stays_explicit_primary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "my-stock-recovery.bin.img"
            image.write_bytes(b"image")
            with prepared_input(image) as (prepared, explicit):
                self.assertEqual(explicit, prepared / image.name)
                self.assertTrue(explicit.is_file())

    def test_bad_input_type_is_explained(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "firmware.tar"
            path.write_bytes(b"x")
            with self.assertRaisesRegex(
                    EasyModeError, "folder, an Android .img file"):
                with_context = prepared_input(path)
                with with_context:
                    pass


if __name__ == "__main__":
    unittest.main()
