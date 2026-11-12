#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    printf '[cloud-slice] ERROR: Python 3 was not found.\n' >&2
    exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 8):
    raise SystemExit(
        f"Python 3.8+ required; found {sys.version.split()[0]}")
PY

if ! PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -c     'import lz4.frame, twrpdtgen.cloud_slice' >/dev/null 2>&1; then
    printf '[cloud-slice] Installing twrpdtgen-NEXT from this clone...\n'
    PIP_DISABLE_PIP_VERSION_CHECK=1 "$PYTHON_BIN" -m pip install -q -e "$ROOT_DIR"
fi

export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON_BIN" -m twrpdtgen.cloud_slice "$@"
