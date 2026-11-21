# SPDX-License-Identifier: Apache-2.0
"""Fresh-clone entrypoint checks; help must work without pip or a network."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class LauncherTests(unittest.TestCase):
    def test_help_works_without_install(self):
        proc = subprocess.run([sys.executable, str(ROOT / "tdtnext.py"), "--help"],
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--input", proc.stdout)
        self.assertIn("--output", proc.stdout)

    def test_version_works_without_install(self):
        proc = subprocess.run([sys.executable, str(ROOT / "tdtnext.py"), "--version"],
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("3.1.0a33", proc.stdout)

if __name__ == "__main__":
    unittest.main()
