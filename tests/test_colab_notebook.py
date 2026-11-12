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


if __name__ == "__main__":
    unittest.main()
