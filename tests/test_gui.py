# SPDX-License-Identifier: Apache-2.0
"""Headless GUI-core tests: importing the GUI must not require X/Tk."""
import tempfile
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from twrpdtgen.gui import GUIJob, GUIResult, can_launch_gui, parse_job, run_job


class GUIBackendTests(unittest.TestCase):
    def test_gui_module_is_importable_on_headless_hosts(self):
        with patch("twrpdtgen.gui.sys.platform", "linux"), \
                patch.dict("twrpdtgen.gui.os.environ", {}, clear=True):
            self.assertFalse(can_launch_gui())

    def test_parse_and_validate_real_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "init_boot.img"
            image.write_bytes(b"sample")
            job = parse_job({
                "source": str(image), "output": str(root / "new-output"),
                "mode": "tree", "recovery_layout": "init_boot",
                "boot_size": "64MiB",
                "skeleton": "twrp-14.1",
                "include_stock_root": True,
            })
            self.assertEqual(job.boot_size, 67108864)
            self.assertEqual(job.recovery_layout, "init_boot")
            self.assertEqual(job.source, image)
            self.assertTrue(job.include_stock_root)
            with self.assertRaisesRegex(ValueError, "source"):
                parse_job({"source": "", "output": str(root)})
            with self.assertRaisesRegex(FileNotFoundError, "Input"):
                GUIJob(root / "absent.img", root / "out").validate()
            with self.assertRaisesRegex(ValueError, "fragment"):
                GUIJob(
                    image, root / "out", recovery_fragment="0",
                    recovery_layout="init_boot").validate()

    def test_tree_zip_and_extract_paths_are_separate(self):
        from unittest.mock import MagicMock
        from twrpdtgen.auto_tree import DiscoveredImages
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "recovery.img"
            image.write_bytes(b"fake")
            output = root / "result"
            discovery = DiscoveredImages(image, image, None, None, None)
            generator = MagicMock()
            generator.dump_to_folder.return_value = output / "samsung/a20s"
            fake_module = types.ModuleType("twrpdtgen.device_tree")
            fake_module.DeviceTree = MagicMock(return_value=generator)
            log = []
            with patch("twrpdtgen.gui._selection") as selection, \
                    patch("twrpdtgen.auto_tree.discover_images", return_value=discovery), \
                    patch.dict(sys.modules, {"twrpdtgen.device_tree": fake_module}), \
                    patch("twrpdtgen.tree_archive.archive_tree",
                          return_value=output / "twrp-device-tree.zip") as zipping:
                selection.return_value.__enter__.return_value = (root, None)
                result = run_job(
                    GUIJob(image, output), log.append)
                self.assertEqual(result.tree, output / "samsung/a20s")
                self.assertEqual(result.archive, output / "twrp-device-tree.zip")
                self.assertIsNone(result.extracted)
                generator.cleanup.assert_called_once()
                zipping.assert_called_once()
                self.assertTrue(any("NOT verified" in x for x in log))

    def test_extraction_does_not_generate_tree(self):
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "init_boot.img"
            source.write_bytes(b"fake")
            extractor = MagicMock()
            extractor.export.side_effect = lambda path: path
            with patch("twrpdtgen.gui._selection") as selection, \
                    patch("twrpdtgen.auto_tree.discover_images",
                          side_effect=ValueError("no recognized images")), \
                    patch("twrpdtgen.boot_image.ModernImageManager",
                          return_value=extractor):
                selection.return_value.__enter__.return_value = (root, source)
                result = run_job(
                    GUIJob(source, root / "output", mode="extract"))
                self.assertTrue(str(result.extracted).endswith("extracted-images"))
                extractor.unpack.assert_called_once()
                extractor.cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
