# SPDX-License-Identifier: Apache-2.0
"""Regression tests for Colab/Debian Python environments lacking ensurepip."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import venv

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tdtnext_launcher", ROOT / "tdtnext.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class ColabBootstrapTests(unittest.TestCase):
    def test_pipless_venv_uses_host_pip_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / "env"
            venv.EnvBuilder(with_pip=False).create(env)
            python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            command = launcher._pip_command(python)
            self.assertEqual(command[:3], [sys.executable, "-m", "pip"])
            self.assertEqual(command[3:], ["--python", str(python)])

    def test_partial_venv_is_reused_after_ensurepip_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / "env"
            python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            original = venv.EnvBuilder

            class FakeBuilder:
                def __init__(self, with_pip):
                    self.with_pip = with_pip

                def create(self, path):
                    original(with_pip=False).create(path)
                    if self.with_pip:
                        raise subprocess.CalledProcessError(1, [str(python), "-m", "ensurepip"])

            with patch.object(launcher, "ENV", env), patch.object(launcher.venv, "EnvBuilder", FakeBuilder):
                launcher._ensure_environment(python)
            self.assertTrue(python.is_file())

    def test_existing_pipless_venv_does_not_retry_ensurepip(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / "env"
            venv.EnvBuilder(with_pip=False).create(env)
            python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            with patch.object(launcher, "ENV", env), patch.object(launcher.venv, "EnvBuilder") as builder:
                launcher._ensure_environment(python)
                builder.assert_not_called()

    def test_install_command_is_editable_and_touches_only_private_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[build-system]\n")
            env = root / ".tdtnext-venv"
            venv.EnvBuilder(with_pip=False).create(env)
            python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            with patch.object(launcher, "ROOT", root), patch.object(launcher, "ENV", env), \
                 patch.object(launcher, "_pip_command", return_value=["host", "-m", "pip", "--python", str(python)]), \
                 patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
                 patch.object(launcher.subprocess, "call", return_value=0):
                result = launcher.main(["--input", "firmware.zip", "--output", "out"])
            self.assertEqual(result, 0)
            install = run.call_args.args[0]
            self.assertIn("-e", install)
            self.assertEqual(install[-1], str(root))
            self.assertTrue((env / ".tdtnext-revision").is_file())


if __name__ == "__main__":
    unittest.main()
