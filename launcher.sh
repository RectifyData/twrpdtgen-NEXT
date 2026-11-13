#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -Eeuo pipefail
IFS=$'\n\t'

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
CALLER_DIR="$PWD"
PYTHON_BIN="${PYTHON_BIN:-python3}"

log() { printf '[twrpdtgen-NEXT] %s\n' "$*"; }
die() { printf '[twrpdtgen-NEXT] ERROR: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

is_colab() {
    [[ -n "${COLAB_RELEASE_TAG:-}" ]] && return 0
    [[ -d /content ]] || return 1
    "$PYTHON_BIN" -c "import google.colab" >/dev/null 2>&1
}

check_python() {
    have "$PYTHON_BIN" || die "Python 3 was not found."
    "$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 8):
    raise SystemExit(f"Python 3.8+ required; found {sys.version.split()[0]}")
PY
}

install_system_dependencies() {
    [[ "${TWRPDTGEN_SKIP_SYSTEM_DEPS:-0}" == "1" ]] && return 0
    have apt-get || { log "apt-get unavailable; skipping system packages."; return 0; }
    local packages=(cpio lz4 xz-utils bzip2 gzip unzip zip file)
    local missing=() package
    if have dpkg; then
        for package in "${packages[@]}"; do
            dpkg -s "$package" >/dev/null 2>&1 || missing+=("$package")
        done
    else
        missing=("${packages[@]}")
    fi
    ((${#missing[@]} == 0)) && { log "System extraction tools already installed."; return 0; }
    local apt=(apt-get)
    if [[ "$(id -u)" -ne 0 ]]; then
        have sudo || die "Missing system tools and neither root nor sudo is available."
        apt=(sudo apt-get)
    fi
    log "Installing missing system tools: ${missing[*]}"
    "${apt[@]}" update
    "${apt[@]}" install -y --no-install-recommends "${missing[@]}"
}

install_python_dependencies() {
    [[ "${TWRPDTGEN_SKIP_PIP:-0}" == "1" ]] && return 0
    log "Installing twrpdtgen-NEXT from this clone..."
    PIP_DISABLE_PIP_VERSION_CHECK=1 "$PYTHON_BIN" -m pip install -e "$ROOT_DIR"
}

doctor() {
    local failed=0 command
    for command in cpio lz4 xz bzip2 gzip unzip zip file; do
        have "$command" || { printf "missing command: %s\n" "$command" >&2; failed=1; }
    done
    PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" - <<'PY' || failed=1
import importlib, sys
for name in ("git", "jinja2", "lz4", "zstandard", "sebaubuntu_libs", "twrpdtgen"):
    importlib.import_module(name)
import twrpdtgen
print("python:", sys.version.split()[0])
print("twrpdtgen-NEXT:", twrpdtgen.__version__)
PY
    ((failed == 0)) || die "Environment check failed."
    log "Environment check passed."
}

self_test() {
    log "Running NEXT regression tests..."
    (
        cd "$ROOT_DIR"
        PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m compileall -q twrpdtgen tests
        PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m unittest discover -s tests -v
    )
}

show_ready() {
    cat <<EOF

twrpdtgen-NEXT is ready.

Colab:
  !git clone https://github.com/RectifyData/twrpdtgen-NEXT.git
  %cd twrpdtgen-NEXT
  !./launcher.sh /content/recovery.img -o /content/output

General form:
  ./launcher.sh [path-to-image-containing-recovery-ramdisk] -o [output-folder]

The output folder is created automatically if it does not exist.

Modern split layout:
  !bash launcher.sh init_boot.img --boot-image boot.img --vendor-boot vendor_boot.img --skeleton twrp-14.1

Extract only:
  !bash launcher.sh init_boot.img --boot-image boot.img --vendor-boot vendor_boot.img --extract-only /content/extracted

Input paths are resolved from:
  $CALLER_DIR

Launcher commands:
  bash launcher.sh --doctor
  bash launcher.sh --self-test
  bash launcher.sh --setup-only

GUI: ./launcher.sh --gui [--source IMAGE]
CLI: ./launcher.sh --cli [IMAGE and options]
All other arguments are passed directly to python3 -m twrpdtgen.
The -o/--output directory does not need to exist beforehand.
EOF
}

main() {
    check_python
    if is_colab; then log "Google Colab detected."; else log "Linux bootstrap mode."; fi
    install_system_dependencies
    install_python_dependencies
    case "${1:-}" in
        --gui)
            shift
            export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
            exec "$PYTHON_BIN" -m twrpdtgen.gui "$@"
            ;;
        --cli)
            shift
            export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
            exec "$PYTHON_BIN" -m twrpdtgen "$@" --cli
            ;;
        --doctor) doctor; return 0 ;;
        --self-test) self_test; return 0 ;;
        --setup-only) doctor; show_ready; return 0 ;;
        "")
            doctor
            if is_colab || [[ ! -t 0 ]]; then
                show_ready
                return 0
            fi
            export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
            if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
                exec "$PYTHON_BIN" -m twrpdtgen.gui
            fi
            exec "$PYTHON_BIN" -m twrpdtgen.easy
            ;;
    esac
    export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
    exec "$PYTHON_BIN" -m twrpdtgen "$@"
}

main "$@"
