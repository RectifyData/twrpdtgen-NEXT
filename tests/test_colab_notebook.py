# SPDX-License-Identifier: Apache-2.0
import ast
import builtins
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


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


    def test_cloud_third_code_cell_has_no_orphaned_configuration(self):
        notebook = json.loads(
            Path("colab/cloud_firmware_slice.ipynb").read_text(
                encoding="utf-8"
            )
        )
        code_cells = [
            "".join(cell["source"]) for cell in notebook["cells"]
            if cell["cell_type"] == "code"
        ]
        self.assertEqual(len(code_cells), 3)
        self.assertTrue(all(
            cell["execution_count"] is None and not cell["outputs"]
            for cell in notebook["cells"] if cell["cell_type"] == "code"
        ))
        source = code_cells[2]
        self.assertNotIn("if version.strip()", source)
        for orphan in (
                "keep_full_firmware_in_colab", "include_stock_root_in_zip",
                "boot_partition_size", "recovery_partition_size",
                "super_partition_size", "dynamic_group_size",
                "download_extracted_image"):
            self.assertNotIn(orphan, source)
        definitions = set(dir(builtins))
        used = set()
        for code in code_cells:
            parsed = ast.parse(code)
            for node in ast.walk(parsed):
                if isinstance(node, ast.Name):
                    if isinstance(node.ctx, ast.Store):
                        definitions.add(node.id)
                    elif isinstance(node.ctx, ast.Load):
                        used.add(node.id)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        definitions.add(
                            alias.asname or alias.name.split(".")[0]
                        )
        self.assertEqual(used - definitions, set())

    def test_cloud_notebook_extraction_and_generation_commands(self):
        notebook = json.loads(
            Path("colab/cloud_firmware_slice.ipynb").read_text(
                encoding="utf-8"
            )
        )
        code = "".join([
            cell for cell in notebook["cells"]
            if cell["cell_type"] == "code"
        ][2]["source"])
        downloads = []
        commands = []

        def run_command(cmd, *, check):
            self.assertTrue(check)
            commands.append(cmd)
            self.assertEqual(cmd[0], sys.executable)
            if "twrpdtgen.cloud_slice" in cmd:
                target = Path(cmd[cmd.index("-o") + 1])
            elif "twrpdtgen.cloud_tree" in cmd:
                target = Path(cmd[cmd.index("--archive") + 1])
            else:
                self.fail("Unexpected command: {!r}".format(cmd))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"synthetic-test-output")

        google = types.ModuleType("google")
        colab = types.ModuleType("google.colab")
        colab.files = types.SimpleNamespace(
            download=lambda path: downloads.append(path)
        )
        google.colab = colab
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            isolated = code.replace("Path('/content')", "Path(workspace)")
            isolated = isolated.replace(
                "Path('/content/twrp-tree')", "workspace / 'twrp-tree'"
            ).replace(
                "Path('/content/twrp-device-tree.zip')",
                "workspace / 'twrp-device-tree.zip'"
            )
            options = {
                "workspace": workspace, "model": "SM-A207F", "region": "NEE",
                "partition": "recovery", "package": "AP", "threads": 8,
                "firmware_version": "", "skeleton": "auto",
                "recovery_layout": "auto", "recovery_root_mode": "minimal",
                "tool_version": "3.1.0a99",
            }
            with patch.dict(sys.modules, {
                    "google": google, "google.colab": colab
            }), patch("subprocess.run", side_effect=run_command):
                exec(isolated, {
                    **options, "workflow": "Extract image only"
                })
                self.assertIn("twrpdtgen.cloud_slice", commands[-1])
                self.assertNotIn("-v", commands[-1])
                self.assertEqual(downloads[-1],
                                 str(workspace / "recovery.img"))

                exec(isolated, {
                    **options, "workflow": "Generate TWRP device tree",
                    "firmware_version": "A207FXXUTEST"
                })
                self.assertIn("twrpdtgen.cloud_tree", commands[-1])
                self.assertEqual(
                    commands[-1][commands[-1].index("-v") + 1],
                    "A207FXXUTEST"
                )
                self.assertEqual(
                    downloads[-1], str(workspace / "twrp-device-tree.zip")
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
