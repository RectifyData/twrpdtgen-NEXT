# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import os
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from twrpdtgen.cloud_slice import SliceResult
from twrpdtgen.cloud_tree import (
    _archive_tree,
    fetch_and_generate_tree,
)


class CloudTreeTests(unittest.TestCase):
    def test_archive_contains_generated_tree_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tree = root / "out" / "samsung" / "a20s"
            tree.mkdir(parents=True)
            (tree / "BoardConfig.mk").write_text(
                "TARGET_BOARD_PLATFORM := msm8953\n",
                encoding="utf-8",
            )
            archive = _archive_tree(tree, root / "result.zip")
            self.assertTrue(archive.is_file())
            with zipfile.ZipFile(archive) as bundle:
                self.assertIn("samsung/a20s/BoardConfig.mk", bundle.namelist())

    def test_archive_preserves_symlinks_and_excludes_stock_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tree = root / "out" / "samsung" / "a20s"
            recovery = tree / "recovery" / "root"
            stock = tree / "recovery" / "stock-root"
            recovery.mkdir(parents=True)
            stock.mkdir(parents=True)
            target = recovery / "prop.default"
            target.write_text("ro.test=1\n", encoding="utf-8")
            link = recovery / "default.prop"
            try:
                link.symlink_to("prop.default")
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            (stock / "secret.bin").write_bytes(b"stock")

            archive = _archive_tree(tree, root / "result.zip")
            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())
                self.assertNotIn(
                    "samsung/a20s/recovery/stock-root/secret.bin",
                    names,
                )
                info = bundle.getinfo(
                    "samsung/a20s/recovery/root/default.prop"
                )
                mode = (info.external_attr >> 16) & 0xFFFF
                self.assertTrue(stat.S_ISLNK(mode))
                self.assertEqual(
                    bundle.read(info).decode("utf-8"),
                    "prop.default",
                )

            archive_with_stock = _archive_tree(
                tree,
                root / "with-stock.zip",
                include_stock_root=True,
            )
            with zipfile.ZipFile(archive_with_stock) as bundle:
                self.assertIn(
                    "samsung/a20s/recovery/stock-root/secret.bin",
                    bundle.namelist(),
                )

    def test_end_to_end_cloud_tree_pipeline_uses_one_firmware_download(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tree_parent = root / "tree-output"
            archive = root / "tree.zip"
            calls = {"download": 0, "slice": 0, "generate": 0}

            def fake_download(model, region, destination, **kwargs):
                calls["download"] += 1
                destination.write_bytes(b"firmware")
                return destination

            def fake_slice(firmware, partition, *, output, **kwargs):
                calls["slice"] += 1
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"ANDROID!fake-recovery")
                return SliceResult(
                    firmware=firmware,
                    package_member="AP_TEST.tar.md5",
                    payload_member="recovery.img.lz4",
                    output=output,
                    output_size=output.stat().st_size,
                    sha256="a" * 64,
                    compression="lz4_legacy",
                )

            def fake_generate(image, tree_output, **kwargs):
                calls["generate"] += 1
                tree = tree_output / "samsung" / "a20s"
                tree.mkdir(parents=True)
                (tree / "AndroidProducts.mk").write_text(
                    "PRODUCT_MAKEFILES := test\n",
                    encoding="utf-8",
                )
                return tree

            with (
                patch(
                    "twrpdtgen.cloud_tree.download_firmware",
                    side_effect=fake_download,
                ),
                patch(
                    "twrpdtgen.cloud_tree.slice_firmware",
                    side_effect=fake_slice,
                ),
                patch(
                    "twrpdtgen.cloud_tree.generate_tree_from_image",
                    side_effect=fake_generate,
                ),
            ):
                result = fetch_and_generate_tree(
                    "SM-A207F",
                    "NEE",
                    tree_output=tree_parent,
                    archive=archive,
                )

            self.assertEqual(calls, {
                "download": 1,
                "slice": 1,
                "generate": 1,
            })
            self.assertTrue(result.archive.is_file())
            self.assertTrue(result.tree.is_dir())
            with zipfile.ZipFile(result.archive) as bundle:
                self.assertIn(
                    "samsung/a20s/AndroidProducts.mk",
                    bundle.namelist(),
                )


if __name__ == "__main__":
    unittest.main()
