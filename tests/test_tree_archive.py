# SPDX-License-Identifier: Apache-2.0
import stat
import tempfile
import unittest
from pathlib import Path
import zipfile

from twrpdtgen.tree_archive import archive_tree


class TreeArchiveTests(unittest.TestCase):
    def test_vendor_neutral_archive_preserves_root_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tree = root / "out" / "google" / "husky"
            recovery = tree / "recovery" / "root"
            stock = tree / "recovery" / "stock-root"
            recovery.mkdir(parents=True)
            stock.mkdir(parents=True)
            (tree / "AndroidProducts.mk").write_text(
                "PRODUCT_MAKEFILES := test\n",
                encoding="utf-8",
            )
            (recovery / "prop.default").write_text(
                "ro.test=1\n",
                encoding="utf-8",
            )
            try:
                (recovery / "default.prop").symlink_to("prop.default")
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            (stock / "audit.bin").write_bytes(b"audit")

            archive = archive_tree(tree, root / "tree.zip")
            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())
                self.assertIn(
                    "google/husky/AndroidProducts.mk",
                    names,
                )
                self.assertNotIn(
                    "google/husky/recovery/stock-root/audit.bin",
                    names,
                )
                info = bundle.getinfo(
                    "google/husky/recovery/root/default.prop"
                )
                mode = (info.external_attr >> 16) & 0xFFFF
                self.assertTrue(stat.S_ISLNK(mode))
                self.assertEqual(
                    bundle.read(info).decode("utf-8"),
                    "prop.default",
                )

    def test_rejects_non_generated_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tree = root / "vendor" / "device"
            tree.mkdir(parents=True)
            with self.assertRaisesRegex(
                    ValueError, "AndroidProducts.mk"):
                archive_tree(tree, root / "tree.zip")


if __name__ == "__main__":
    unittest.main()
