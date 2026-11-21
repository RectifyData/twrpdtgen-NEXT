# SPDX-License-Identifier: Apache-2.0
"""On-demand, unprivileged installation of a verified Python lpunpack.

The native lpunpack executable on PATH always takes precedence. When absent,
install liblp only after an actual super.img is discovered. The install uses
pip's hash checking and --target to avoid modifying the system Python or
requiring administrator privileges. No install runs for --help or ordinary boot
images. All downloads and installer output remain visible in the console.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import List, Tuple

LIBLP_VERSION = '1.0.2'
# The SHA-256 of the official universal liblp wheel published on PyPI.
LIBLP_WHEEL_SHA256 = 'beb3469f61a12c3f9ea941967a8fa4f9bf37cce486b1fe75c9d60f2db2f8ef4c'
# The Python distribution exposes the CLI entrypoint as this import.
BOOTSTRAP_CODE = (
    'import sys; '
    'sys.path.insert(0, sys.argv[1]); '
    'from liblp.partition_tools.lpunpack import main; '
    'sys.argv = ["lpunpack"] + sys.argv[2:]; '
    'main()'
)


class ToolInstallError(RuntimeError):
    """The user-scoped dependency could not be prepared."""


def _cache_root() -> Path:
    configured = os.environ.get('XDG_CACHE_HOME', '')
    if configured and Path(configured).is_absolute():
        return Path(configured).expanduser() / 'tdtnext' / 'tools'
    return Path.home() / '.cache' / 'tdtnext' / 'tools'


def _local_lpunpack() -> Tuple[List[str], str] | None:
    native = shutil.which('lpunpack')
    if native:
        return [native], native
    return None


def _cached_liblp_tool(target: Path) -> Tuple[List[str], str] | None:
    # Never trust an interrupted installation or merely a nonempty folder.
    if target.is_symlink() or not (target / '.tdtnext-installed').is_file():
        return None
    if not (target / 'liblp' / 'partition_tools' / 'lpunpack.py').is_file():
        return None
    return ([sys.executable, '-c', BOOTSTRAP_CODE, str(target)],
            'Python liblp ' + LIBLP_VERSION + ' (user cache: ' + str(target) + ')')


def find_lpunpack(*, auto_install: bool = True) -> Tuple[List[str], str]:
    """Find a system tool or safely install liblp in the user's cache.

    Returns a command prefix and a readable provenance description.
    The prefix can be followed by SUPER_IMAGE and OUTPUT_DIR arguments.
    """
    existing = _local_lpunpack()
    if existing:
        return existing

    root = _cache_root()
    target = root / ('liblp-' + LIBLP_VERSION)
    cached = _cached_liblp_tool(target)
    if cached:
        return cached
    if not auto_install:
        raise ToolInstallError(
            'lpunpack is missing. Auto-installation is disabled (--no-auto-install). '
            'Install liblp or Android lpunpack yourself, or rerun without this option.')

    print('lpunpack not found. Installing verified Python liblp ' + LIBLP_VERSION
          + ' in your user cache (no sudo required).', flush=True)
    root.mkdir(parents=True, exist_ok=True)
    # The staging directory lives alongside the final cache path, enabling an
    # atomic rename after pip succeeds and the entrypoint has been checked.
    with tempfile.TemporaryDirectory(prefix='.liblp-install-', dir=root) as scratch:
        staged = Path(scratch) / 'package'
        staged.mkdir()
        req = Path(scratch) / 'requirements.txt'
        req.write_text('liblp==' + LIBLP_VERSION + ' --hash=sha256:'
                       + LIBLP_WHEEL_SHA256 + '\n', encoding='ascii')
        cmd = [sys.executable, '-m', 'pip', 'install',
               '--disable-pip-version-check', '--no-input',
               '--require-hashes', '--no-deps', '--only-binary=:all:',
               '--target', str(staged), '-r', str(req)]
        try:
            # Do not suppress progress or prompt for elevated permissions.
            result = subprocess.run(cmd, check=False)
        except OSError as exc:
            raise ToolInstallError('Unable to run Python pip: ' + str(exc)) from exc
        if result.returncode:
            raise ToolInstallError(
                'Automatic lpunpack installation failed (pip exit ' +
                str(result.returncode) + '). Check network access and ensure '
                'python3-pip is installed; the system was not modified.')
        entrypoint = staged / 'liblp' / 'partition_tools' / 'lpunpack.py'
        if not entrypoint.is_file():
            raise ToolInstallError('Installed liblp is missing its lpunpack entrypoint')
        (staged / '.tdtnext-installed').write_text(
            'liblp==' + LIBLP_VERSION + '\nsha256=' + LIBLP_WHEEL_SHA256 + '\n',
            encoding='ascii')
        if target.exists():
            # An interrupted cache from a previous attempt may be incomplete.
            # Preserve any directory not created by tdtnext rather than removing it.
            marker = target / '.tdtnext-installed'
            if not marker.is_file():
                raise ToolInstallError(
                    'Existing liblp cache folder is not managed by tdtnext: ' + str(target))
            shutil.rmtree(target)
        os.replace(staged, target)
    prepared = _cached_liblp_tool(target)
    if prepared is None:
        raise ToolInstallError('Installed liblp could not be located after installation')
    print('lpunpack installed in ' + str(target), flush=True)
    return prepared

# Filesystem utilities are needed only for actual ext4/EROFS partitions.
# On Windows prefer native binaries, then a supported Ubuntu WSL environment.
# WSL feature setup is intentionally visible, with no implicit restart.
EXTRACTORS = {'debugfs': 'e2fsprogs', 'fsck.erofs': 'erofs-utils'}


def _on_windows() -> bool:
    return sys.platform == 'win32'


def _run_visible(command: List[str], label: str) -> None:
    print('[tdtnext] Installing ' + label + ': ' + ' '.join(command), flush=True)
    try:
        result = subprocess.run(command, check=False)
    except OSError as exc:
        raise ToolInstallError('Could not launch installer for ' + label + ': ' + str(exc)) from exc
    if result.returncode:
        raise ToolInstallError(label + ' installer exited with code ' + str(result.returncode)
                               + '. Review the installer output above.')


def _run_probe(command: List[str]) -> bool:
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors='replace', check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _system_package_command(executable: str) -> List[str]:
    package = EXTRACTORS[executable]
    manager = next((name for name in ('apt-get', 'dnf', 'pacman', 'zypper', 'apk')
                    if shutil.which(name)), None)
    if not manager:
        raise ToolInstallError('Cannot auto-install ' + executable + ': unsupported Linux package manager. '
                               'Install ' + package + ' from your distribution manually.')
    prefix = [] if (hasattr(os, 'geteuid') and os.geteuid() == 0) else ['sudo']
    if prefix and not shutil.which('sudo'):
        raise ToolInstallError('Cannot auto-install ' + package + ': sudo is not available.')
    options = {
        'apt-get': ['apt-get', 'install', '-y', package],
        'dnf': ['dnf', 'install', '-y', package],
        'pacman': ['pacman', '-S', '--noconfirm', package],
        'zypper': ['zypper', '--non-interactive', 'install', package],
        'apk': ['apk', 'add', package],
    }
    # sudo inherits the user's terminal; progress and password requests are visible.
    return prefix + options[manager]


def _ensure_wsl(*, auto_install: bool) -> str:
    launcher = shutil.which('wsl.exe') or shutil.which('wsl')
    if not launcher:
        raise ToolInstallError('This Windows installation has no WSL launcher. '
                               'Enable Windows Subsystem for Linux with Microsoft WSL first.')
    if _run_probe([launcher, '--exec', 'sh', '-c', 'true']):
        return launcher
    if not auto_install:
        raise ToolInstallError('WSL Ubuntu is missing or not initialized, and auto-install is disabled.')
    print('[tdtnext] Native Linux filesystem support is unavailable on Windows.\n'
          'Installing Microsoft WSL with Ubuntu. Windows may request administrator '
          'approval, Linux username setup, or a restart. No reboot will be initiated.', flush=True)
    # Enabling Windows features needs elevation. Launch a *visible* elevated
    # PowerShell process so Windows itself displays the UAC approval dialog.
    powershell = shutil.which('powershell.exe') or 'powershell.exe'
    elevated = (
        "$p = Start-Process -FilePath 'wsl.exe' "
        "-ArgumentList @('--install','-d','Ubuntu') "
        "-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
    )
    _run_visible([powershell, '-NoProfile', '-Command', elevated],
                 'Microsoft WSL Ubuntu (administrator approval required)')
    if not _run_probe([launcher, '--exec', 'sh', '-c', 'true']):
        raise ToolInstallError('WSL was requested but Ubuntu is not ready. Complete the Windows '
                               'restart/first-run setup if prompted, then retry tdtnext.')
    return launcher


def _wsl_package_install(launcher: str, executable: str) -> None:
    # Current default distro must be Debian/Ubuntu for this automatic path.
    if not _run_probe([launcher, '--exec', 'sh', '-c', 'command -v apt-get >/dev/null']):
        raise ToolInstallError('The default WSL distribution is not Debian/Ubuntu. '
                               'Install ' + EXTRACTORS[executable] + ' using its Linux package manager.')
    command = [launcher, '--exec']
    # sudo is a visible interactive prompt, never background elevation.
    if not _run_probe([launcher, '--exec', 'sh', '-c', '[ "$(id -u)" = 0 ]']):
        if not _run_probe([launcher, '--exec', 'sh', '-c', 'command -v sudo >/dev/null']):
            raise ToolInstallError('WSL user cannot install ' + EXTRACTORS[executable]
                                   + ' because it has neither root privileges nor sudo.')
        command += ['sudo']
    command += ['apt-get', 'install', '-y', EXTRACTORS[executable]]
    _run_visible(command, 'WSL ' + EXTRACTORS[executable])


def find_extractor(executable: str, *, auto_install: bool = True) -> Tuple[List[str], str, bool]:
    """Return command prefix, provenance, and a flag for Windows-to-WSL translation.

    Does not alter the user's PATH or install anything unless missing and
    auto_install is explicitly enabled (the default for firmware processing).
    """
    if executable not in EXTRACTORS:
        raise ValueError('Unrecognized extractor: ' + executable)
    native = shutil.which(executable)
    if native:
        return [native], native, False
    if _on_windows():
        # Existing WSL tools are allowed even with --no-auto-install.
        # Only provision WSL itself when it is absent and installation is allowed.
        launcher = _ensure_wsl(auto_install=auto_install)
        probe = [launcher, '--exec', 'sh', '-c', 'command -v ' + executable + ' >/dev/null']
        if not _run_probe(probe):
            if not auto_install:
                raise ToolInstallError(executable + ' is missing from WSL and --no-auto-install was set')
            _wsl_package_install(launcher, executable)
        if not _run_probe(probe):
            raise ToolInstallError('Could not locate ' + executable + ' after installing it in WSL')
        return [launcher, '--exec', executable], 'WSL ' + executable, True
    if not auto_install:
        raise ToolInstallError(executable + ' is missing and --no-auto-install was set')
    _run_visible(_system_package_command(executable), EXTRACTORS[executable])
    native = shutil.which(executable)
    if not native:
        raise ToolInstallError(executable + ' was installed but cannot be found in PATH')
    return [native], native, False


def translated_path(path: Path, *, via_wsl: bool) -> str:
    """Convert an absolute Windows path to the default WSL distro's view."""
    if not via_wsl:
        return str(path)
    launcher = shutil.which('wsl.exe') or shutil.which('wsl')
    if not launcher:
        raise ToolInstallError('WSL disappeared while extracting a partition')
    try:
        process = subprocess.run([launcher, '--exec', 'wslpath', '-a', '-u', str(Path(path).resolve())],
                                 capture_output=True, text=True, errors='replace',
                                 timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolInstallError('Could not convert path for WSL: ' + str(exc)) from exc
    result = process.stdout.strip()
    if process.returncode or not result.startswith('/'):
        raise ToolInstallError('WSL could not access this Windows path: ' + str(path)
                               + '\n' + process.stderr.strip())
    return result


def install_all_tools(*, auto_install: bool = True) -> dict:
    """Visible optional preparatory install, for `tdtnext --setup-tools`."""
    installed = {}
    _, label = find_lpunpack(auto_install=auto_install)
    installed['lpunpack'] = label
    for executable in EXTRACTORS:
        _, label, _ = find_extractor(executable, auto_install=auto_install)
        installed[executable] = label
    return installed
