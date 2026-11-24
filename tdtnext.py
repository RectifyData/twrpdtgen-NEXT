#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Start tdtnext directly from a fresh Git clone with no manual pip steps."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".tdtnext-venv"

def _python():
    return ENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

def _ready(py):
    marker = ENV / ".tdtnext-revision"
    if not py.is_file() or not marker.is_file():
        return False
    try:
        return marker.read_text(encoding="ascii") == str((ROOT / "pyproject.toml").stat().st_mtime_ns)
    except (OSError, ValueError):
        return False

def _ensure_environment(py):
    """Survive Colab/Debian Python builds where venv exists but ensurepip fails."""
    if py.is_file():
        return
    try:
        venv.EnvBuilder(with_pip=True).create(ENV)
    except (OSError, subprocess.CalledProcessError) as exc:
        print("[tdtnext] ensurepip unavailable; using a pip-free virtual environment.", flush=True)
        try:
            # The failed ensurepip attempt may already have created bin/python.
            # Rebuild without pip instead of asking the user to install packages.
            venv.EnvBuilder(with_pip=False).create(ENV)
        except (OSError, subprocess.CalledProcessError) as fallback:
            raise RuntimeError("Could not create a virtual environment: " + str(fallback)) from exc
    if not py.is_file():
        raise RuntimeError("Virtual environment has no Python interpreter: " + str(py))


def _pip_command(py):
    """Use venv pip or bootstrap a pipless venv using host pip --python."""
    try:
        has_pip = subprocess.run(
            [str(py), "-m", "pip", "--version"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False).returncode == 0
    except OSError:
        has_pip = False
    if has_pip:
        return [str(py), "-m", "pip"]
    print("[tdtnext] Installing into the isolated environment using host pip --python.", flush=True)
    # pip >=22.3 supports --python even when the target venv lacks ensurepip.
    return [sys.executable, "-m", "pip", "--python", str(py)]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv or "--version" in argv:
        from twrpdtgen.main import build_parser
        if "--version" in argv:
            from twrpdtgen import __version__
            print("tdtnext " + __version__)
        else:
            parser = build_parser()
            parser.prog = "tdtnext"
            parser.print_help()
        return 0
    if sys.version_info < (3, 9):
        print("tdtnext requires Python 3.9 or newer.", file=sys.stderr)
        return 2
    py = _python()
    if not _ready(py):
        print("[tdtnext] First run: preparing an isolated Python environment.", flush=True)
        try:
            _ensure_environment(py)
            pip_command = _pip_command(py)
            print("[tdtnext] Installing dependencies with visible progress...", flush=True)
            # Editable source makes git pull updates immediately usable.
            completed = subprocess.run(
                [*pip_command, "install", "--disable-pip-version-check",
                 "--upgrade", "-e", str(ROOT)], cwd=ROOT, check=False)
            if completed.returncode:
                print("[tdtnext] Dependency installation failed (exit "
                      + str(completed.returncode) + "). System Python was not modified.",
                      file=sys.stderr)
                return completed.returncode
            (ENV / ".tdtnext-revision").write_text(
                str((ROOT / "pyproject.toml").stat().st_mtime_ns), encoding="ascii")
        except (OSError, RuntimeError) as exc:
            print("[tdtnext] Setup failed: " + str(exc), file=sys.stderr)
            print("[tdtnext] Check python3 -m pip --version (host pip 22.3+ is "
                  "required if ensurepip is unavailable).", file=sys.stderr)
            return 2
    if argv == ["--setup-only"]:
        print("[tdtnext] Isolated environment ready: " + str(py), flush=True)
        return 0
    return subprocess.call([str(py), "-m", "twrpdtgen", "--cli", *argv])

if __name__ == "__main__":
    raise SystemExit(main())
