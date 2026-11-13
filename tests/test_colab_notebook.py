# SPDX-License-Identifier: Apache-2.0
import json
import unittest
from pathlib import Path


class ColabNotebookTests(unittest.TestCase):
    def test_cloud_notebook_uses_fresh_python_processes(self):
        notebook = json.loads(
            Path("colab/cloud_firmware_slice.ipynb").read_text(
                encoding="utf-8"
            )
        )
        source = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
            if cell.get("cell_type") == "code"
        )
        self.assertIn(
            "[sys.executable, '-m', 'twrpdtgen.cloud_slice', *args]",
            source,
        )
        self.assertIn(
            "[sys.executable, '-m', 'twrpdtgen.cloud_tree', *args]",
            source,
        )
        self.assertNotIn(
            "from twrpdtgen.cloud_slice import main as cloud_slice_main",
            source,
        )
        self.assertNotIn(
            "from twrpdtgen.cloud_tree import main as cloud_tree_main",
            source,
        )
        self.assertIn(
            "import twrpdtgen; print(twrpdtgen.__version__)",
            source,
        )


    def test_generic_notebook_is_vendor_neutral_and_fresh_process(self):
        notebook = json.loads(
            Path("colab/generic_image_to_tree.ipynb").read_text(
                encoding="utf-8"
            )
        )
        source = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
            if cell.get("cell_type") == "code"
        )
        self.assertIn(
            "sys.executable, '-m', 'twrpdtgen.auto_tree'",
            source,
        )
        self.assertIn("files.upload()", source)
        self.assertIn("zipfile.is_zipfile", source)
        self.assertNotIn("primary_image =", source)
        self.assertNotIn("boot_image =", source)
        self.assertNotIn("vendor_boot_image =", source)
        self.assertNotIn("init_boot_image =", source)
        self.assertNotIn("samloader", source.lower())
        self.assertNotIn("SM-A207F", source)


if __name__ == "__main__":
    unittest.main()
