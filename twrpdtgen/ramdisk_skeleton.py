# Copyright (C) 2026 The twrpdtgen-NEXT contributors
# SPDX-License-Identifier: Apache-2.0
"""Turn an extracted stock recovery ramdisk into a safe TWRP tree skeleton."""

from dataclasses import dataclass, field
import fnmatch
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
from typing import List


@dataclass
class RamdiskCopyReport:
    copied_files: List[str] = field(default_factory=list)
    copied_symlinks: List[str] = field(default_factory=list)
    copied_dirs: List[str] = field(default_factory=list)
    skipped_special: List[str] = field(default_factory=list)

    def as_dict(self):
        return {
            "copied_files": self.copied_files,
            "copied_symlinks": self.copied_symlinks,
            "copied_dirs": self.copied_dirs,
            "skipped_special": self.skipped_special,
        }


# Files that are normally device additions rather than the recovery program
# supplied by AOSP/TWRP itself. Auto mode deliberately stays conservative for
# complete stock recovery/boot ramdisks so it does not replace TWRP's own init,
# recovery binary, adbd, toybox, UI resources or generic framework files.
_ROOT_PATTERNS = (
    "fstab.*",
    "ueventd.*.rc",
    "init.recovery.*.rc",
    "init.*.usb.rc",
    "init.*.usb.configfs.rc",
)

_SAFE_SUBTREES = (
    "vendor",
    "odm",
    "vendor_dlkm",
    "odm_dlkm",
)

_SAFE_PATH_PREFIXES = (
    "lib/modules/",
    "lib64/modules/",
    "system/etc/vintf/",
    "system/etc/firmware/",
    "system/lib/modules/",
    "system/lib64/modules/",
)


def _relative_name(path: Path) -> str:
    return path.as_posix().lstrip("./")


def _ensure_real_directory(path: Path):
    """Create path while replacing symlink ancestors instead of following them."""
    pending = []
    cursor = path
    while not cursor.exists() and not cursor.is_symlink():
        pending.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    if cursor.is_symlink():
        cursor.unlink()
        cursor.mkdir()
    elif cursor.exists() and not cursor.is_dir():
        cursor.unlink()
        cursor.mkdir()
    for directory in reversed(pending):
        if directory.is_symlink():
            directory.unlink()
        if not directory.exists():
            directory.mkdir()


def _copy_one(source: Path, destination: Path, report: RamdiskCopyReport):
    """Copy a regular file/directory/symlink without following source symlinks."""
    info = source.lstat()
    mode = info.st_mode
    if stat.S_ISLNK(mode):
        _ensure_real_directory(destination.parent)
        target = PurePosixPath(str(source.readlink()))
        if target.is_absolute() or ".." in target.parts:
            report.skipped_special.append(destination.as_posix())
            return
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        destination.symlink_to(str(target))
        report.copied_symlinks.append(destination.as_posix())
        return
    if stat.S_ISDIR(mode):
        _ensure_real_directory(destination.parent)
        if destination.is_symlink():
            destination.unlink()
        elif destination.exists() and not destination.is_dir():
            destination.unlink()
        destination.mkdir(parents=False, exist_ok=True)
        try:
            destination.chmod(stat.S_IMODE(mode))
        except OSError:
            pass
        report.copied_dirs.append(destination.as_posix())
        return
    if stat.S_ISREG(mode):
        _ensure_real_directory(destination.parent)
        if destination.is_symlink():
            destination.unlink()
        elif destination.exists() and destination.is_dir():
            shutil.rmtree(destination)
        shutil.copy2(source, destination, follow_symlinks=False)
        report.copied_files.append(destination.as_posix())
        return
    report.skipped_special.append(destination.as_posix())


def copy_ramdisk_tree(
        source: Path,
        destination: Path,
        include=None) -> RamdiskCopyReport:
    """Copy an extracted ramdisk safely and quickly.

    include receives a POSIX relative path and may reject entries. Directories
    are traversed even when the directory itself is not selected so a selected
    child can still be copied.
    """
    source = Path(source)
    destination = Path(destination)
    report = RamdiskCopyReport()
    if not source.is_dir():
        raise ValueError(f"Ramdisk root is not a directory: {source}")
    destination.mkdir(parents=True, exist_ok=True)

    stack = [(source, Path())]
    while stack:
        current, relative_dir = stack.pop()
        entries = list(current.iterdir())
        for entry in entries:
            relative = relative_dir / entry.name
            rel_name = _relative_name(relative)
            info = entry.lstat()
            if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                stack.append((entry, relative))
                if include is None or include(rel_name + "/"):
                    _copy_one(entry, destination / relative, report)
                continue
            if include is not None and not include(rel_name):
                continue
            _copy_one(entry, destination / relative, report)

    # Keep manifests deterministic and portable: record paths relative to the
    # generated ramdisk root rather than machine-specific output directories.
    for attribute in (
            "copied_files", "copied_symlinks",
            "copied_dirs", "skipped_special"):
        values = getattr(report, attribute)
        setattr(
            report,
            attribute,
            [
                Path(value).relative_to(destination).as_posix()
                for value in values
            ])
    return report


def is_device_overlay_path(relative: str) -> bool:
    """Select device-specific recovery payload without replacing TWRP itself."""
    relative = relative.rstrip("/")
    if not relative:
        return False
    parts = relative.split("/")
    top = parts[0]
    if top in _SAFE_SUBTREES:
        return True
    if any(relative.startswith(prefix) for prefix in _SAFE_PATH_PREFIXES):
        return True
    if len(parts) == 1:
        return any(fnmatch.fnmatch(parts[0], pattern) for pattern in _ROOT_PATTERNS)
    return False


def _merge_report(target: RamdiskCopyReport, source: RamdiskCopyReport):
    target.copied_files.extend(source.copied_files)
    target.copied_symlinks.extend(source.copied_symlinks)
    target.copied_dirs.extend(source.copied_dirs)
    target.skipped_special.extend(source.skipped_special)


def materialize_recovery_skeleton(
        sources,
        stock_root: Path,
        build_root: Path,
        mode: str) -> dict:
    """Persist exact recovery files and seed the build overlay.

    Multiple source roots are overlaid in the supplied order, matching the
    effective ramdisk view used by the generator.
    """
    if mode not in ("full", "minimal"):
        raise ValueError(f"Unknown recovery root mode: {mode}")
    if isinstance(sources, (str, Path)):
        sources = [Path(sources)]
    else:
        sources = [Path(source) for source in sources]
    if not sources:
        raise ValueError("No recovery ramdisk sources selected")

    stock_report = RamdiskCopyReport()
    overlay_report = RamdiskCopyReport()
    for source in sources:
        _merge_report(
            stock_report,
            copy_ramdisk_tree(source, stock_root))
        _merge_report(
            overlay_report,
            copy_ramdisk_tree(
                source,
                build_root,
                include=None if mode == "full" else is_device_overlay_path))
    return {
        "mode": mode,
        "source_count": len(sources),
        "stock_root": "recovery/stock-root",
        "build_root": "recovery/root",
        "stock": stock_report.as_dict(),
        "overlay": overlay_report.as_dict(),
    }


def write_ramdisk_manifest(path: Path, data: dict):
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
