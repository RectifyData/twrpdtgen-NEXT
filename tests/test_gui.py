# SPDX-License-Identifier: Apache-2.0
"""Headless tests ensuring CLI and both GUIs share one option/runtime contract."""
import tempfile
import unittest
from argparse import ArgumentParser
from pathlib import Path
from unittest.mock import patch

from twrpdtgen.auto_tree import DiscoveredImages
from twrpdtgen.gui import GUIJob, can_launch_gui, parse_job, run_job
from twrpdtgen.main import CLIExecutionResult, build_parser
from twrpdtgen.option_sync import (
    _FIXED, extra_cli_argv, interface_schema, validate_extra_values,
)


class GUIBackendTests(unittest.TestCase):
    def test_gui_import_does_not_need_desktop(self):
        with patch("twrpdtgen.gui.sys.platform", "linux"), \
                patch.dict("twrpdtgen.gui.os.environ", {}, clear=True):
            self.assertFalse(can_launch_gui())

    def test_gui_options_cover_every_cli_flag(self):
        parser = build_parser()
        schema = interface_schema()
        exposed = {spec["name"] for spec in schema["extras"]}
        for action in parser._actions:
            if not action.option_strings or action.dest in ("help", "gui", "web", "cli"):
                continue
            self.assertTrue(
                action.dest in _FIXED or action.dest in exposed,
                msg="CLI flag missing from the GUI: {}".format(action.dest))
        for name in ("skeleton", "recovery_layout", "recovery_root_mode"):
            cli_action = next(a for a in parser._actions if a.dest == name)
            self.assertEqual(schema["choices"][name]["choices"],
                             [str(c) for c in cli_action.choices])
        self.assertTrue({"git", "debug", "extract_to"}.issubset(exposed))

    def test_new_future_flag_is_automatically_exposed_and_parsed(self):
        parser = build_parser()
        parser.add_argument("--future-color", choices=("blue", "red"),
                            default="blue")
        parser.add_argument("--future-depth", type=int, default=1)
        with patch("twrpdtgen.main.build_parser", return_value=parser):
            schema = interface_schema()
            extras = {item["name"]: item for item in schema["extras"]}
            self.assertEqual(extras["future_color"]["choices"], ["blue", "red"])
            self.assertEqual(extras["future_depth"]["kind"], "text")
            from_gui = {"future_color": "red", "future_depth": "7"}
            self.assertEqual(validate_extra_values(from_gui), from_gui)
            parsed = parser.parse_args([
                "recovery.img", *extra_cli_argv(from_gui)])
            self.assertEqual(parsed.future_color, "red")
            self.assertEqual(parsed.future_depth, 7)

    def test_unsupported_option_shape_fails_loudly(self):
        parser = build_parser()
        parser.add_argument("--future-items", nargs="+")
        with patch("twrpdtgen.main.build_parser", return_value=parser):
            with self.assertRaisesRegex(ValueError, "Unsupported CLI option"):
                interface_schema()

    def test_parse_and_validate_real_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "init_boot.img"
            image.write_bytes(b"sample")
            job = parse_job({
                "source": str(image), "output": str(root / "new-output"),
                "mode": "tree", "recovery_layout": "init_boot",
                "boot_size": "64MiB", "skeleton": "twrp-14.1",
                "include_stock_root": True,
                "cli_options": {"git": False, "debug": True},
            })
            self.assertEqual(job.boot_size, 67108864)
            self.assertEqual(dict(job.cli_options)["debug"], True)
            self.assertTrue(job.include_stock_root)
            with self.assertRaisesRegex(ValueError, "source"):
                parse_job({"source": "", "output": str(root)})
            with self.assertRaisesRegex(FileNotFoundError, "Input"):
                GUIJob(root / "absent.img", root / "out").validate()
            with self.assertRaisesRegex(ValueError, "Unknown GUI CLI options"):
                GUIJob(image, root / "out",
                       cli_options=(("unsafe_unknown", "payload"),)).validate()
            with self.assertRaisesRegex(ValueError, "fragment"):
                GUIJob(image, root / "out", recovery_fragment="0",
                       recovery_layout="init_boot").validate()

    def test_gui_tree_dispatches_to_same_cli_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "recovery.img"
            image.write_bytes(b"fake")
            output = root / "result"
            tree = output / "samsung" / "a20s"
            discovery = DiscoveredImages(image, image, None, None, None)
            logs = []
            with patch("twrpdtgen.gui._selection") as selection, \
                    patch("twrpdtgen.auto_tree.discover_images",
                          return_value=discovery), \
                    patch("twrpdtgen.main.execute_cli_job",
                          return_value=CLIExecutionResult(tree=tree)) as run_cli, \
                    patch("twrpdtgen.tree_archive.archive_tree",
                          return_value=output / "twrp-device-tree.zip") as zip_tree:
                selection.return_value.__enter__.return_value = (root, None)
                result = run_job(GUIJob(
                    image, output,
                    cli_options=(("git", True), ("debug", True))), logs.append)
                self.assertEqual(result.tree, tree)
                self.assertEqual(result.archive, output / "twrp-device-tree.zip")
                self.assertTrue(output.is_dir())
                args = run_cli.call_args.args[0]
                self.assertEqual(args.image, image)
                self.assertEqual(args.output, output)
                self.assertTrue(args.git)
                self.assertTrue(args.debug)
                self.assertTrue(run_cli.call_args.kwargs["direct"])
                zip_tree.assert_called_once()
                self.assertTrue(any("NOT verified" in line for line in logs))

    def test_gui_extracts_using_cli_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "init_boot.img"
            image.write_bytes(b"fake")
            output = root / "result"
            target = output / "extracted-images"
            with patch("twrpdtgen.gui._selection") as selection, \
                    patch("twrpdtgen.auto_tree.discover_images",
                          side_effect=ValueError("no recognized images")), \
                    patch("twrpdtgen.main.execute_cli_job",
                          return_value=CLIExecutionResult(extracted=target)) as run_cli:
                selection.return_value.__enter__.return_value = (root, image)
                result = run_job(GUIJob(image, output, mode="extract"))
                self.assertEqual(result.extracted, target)
                self.assertEqual(run_cli.call_args.args[0].extract_only, target)


if __name__ == "__main__":
    unittest.main()
