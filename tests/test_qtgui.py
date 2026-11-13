# SPDX-License-Identifier: Apache-2.0
"""PyQt5 headless smoke and CLI option synchronization tests."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from twrpdtgen.qtgui import create_window, qt_available


@unittest.skipUnless(qt_available(), "PyQt5 plus graphical/offscreen platform required")
class QtUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_window_renders_and_has_working_generator_controls(self):
        window = create_window()
        try:
            data = window.values()
            for key in (
                    "source", "output", "boot_image", "vendor_boot",
                    "init_boot", "skeleton", "recovery_layout",
                    "recovery_root_mode", "recovery_fragment", "mode"):
                self.assertIn(key, data)
            self.assertEqual(data["mode"], "tree")
            self.assertIn("init_boot",
                          [window.fields["recovery_layout"].itemText(i)
                           for i in range(window.fields["recovery_layout"].count())])
            self.assertTrue({"debug", "git", "extract_to"}
                            .issubset(data["cli_options"]))
            menu = [item.text() for item in window.tools.menu().actions()]
            self.assertIn("Check Git updates", menu)
            self.assertIn("Update from Git…", menu)
            self.assertFalse(window.busy)
        finally:
            window.close()

    def test_new_cli_option_auto_appears_in_qt(self):
        from twrpdtgen.main import build_parser
        parser = build_parser()
        parser.add_argument("--new-qt-setting", choices=("a", "b"), default="a")
        with patch("twrpdtgen.main.build_parser", return_value=parser):
            window = create_window()
        try:
            self.assertIn("new_qt_setting", window.extras)
            self.assertEqual(window.values()["cli_options"]["new_qt_setting"], "a")
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
