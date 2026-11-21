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
            if not py.exists():
                venv.EnvBuilder(with_pip=True).create(ENV)
        except Exception as exc:
            print("[tdtnext] Virtual environment creation failed: " + str(exc), file=sys.stderr)
            print("[tdtnext] On Ubuntu/Debian, install python3-venv and retry.", file=sys.stderr)
            return 2
        print("[tdtnext] Installing dependencies with visible progress...", flush=True)
        completed = subprocess.run(
            [str(py), "-m", "pip", "install", "--disable-pip-version-check",
             "--upgrade", str(ROOT)], cwd=ROOT, check=False)
        if completed.returncode:
            print("[tdtnext] Installation failed; system Python was not modified.", file=sys.stderr)
            return completed.returncode
        (ENV / ".tdtnext-revision").write_text(
            str((ROOT / "pyproject.toml").stat().st_mtime_ns), encoding="ascii")
    return subprocess.call([str(py), "-m", "twrpdtgen", "--cli", *argv])

if __name__ == "__main__":
    raise SystemExit(main())
