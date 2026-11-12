#
# Copyright (C) 2026 The twrpdtgen-NEXT contributors
#
# SPDX-License-Identifier: Apache-2.0
#
"""Conservative skeleton and metadata choices for generated recovery trees."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Iterable, Optional


_API_KEYS = (
    "ro.build.version.sdk",
    "ro.vendor.build.version.sdk",
    "ro.system.build.version.sdk",
    "ro.product.build.version.sdk",
)
_PROPERTY_PATHS = (
    "default.prop",
    "prop.default",
    "system/build.prop",
    "vendor/build.prop",
    "system/etc/build.prop",
    "vendor/etc/build.prop",
    "first_stage_ramdisk/prop.default",
    "system/etc/prop.default",
    "system/system/build.prop",
    "vendor/default.prop",
)
_NAME = re.compile(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]*\Z")
_PART = re.compile(r"[a-zA-Z0-9_]+\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def parse_partition_size(value: str) -> int:
    """Parse bytes (decimal/hex); reject bogus or unaligned geometry."""
    try:
        result = int(value, 0)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "Partition size must be an integer byte count") from exc
    if result <= 0 or result % 4096:
        raise ValueError(
            "Partition size must be positive and 4096-byte aligned")
    return result


@dataclass(frozen=True)
class NextOptions:
    skeleton: str = "auto"
    recovery_layout: str = "auto"
    boot_size: Optional[int] = None
    recovery_size: Optional[int] = None
    super_size: Optional[int] = None
    dynamic_group_size: Optional[int] = None
    overwrite: bool = False

    def __post_init__(self):
        if self.skeleton not in (
                "auto", "omni", "twrp-12.1", "twrp-14.1"):
            raise ValueError("Unknown skeleton")
        if self.recovery_layout not in (
                "auto", "dedicated", "boot", "vendor_boot"):
            raise ValueError("Unknown recovery layout")
        for name in (
                "boot_size", "recovery_size",
                "super_size", "dynamic_group_size"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, int) or isinstance(value, bool):
                    raise ValueError(
                        f"{name} must be a byte count")
                parse_partition_size(str(value))
        if (
                self.super_size is not None
                and self.dynamic_group_size is not None
                and self.dynamic_group_size >= self.super_size):
            raise ValueError(
                "Dynamic group must be smaller than the super partition")


def safe_component(value: str) -> str:
    """Reject values that could escape output/manufacturer/codename."""
    if (
            not isinstance(value, str)
            or not _NAME.fullmatch(value)
            or value in (".", "..")):
        raise ValueError(
            f"Unsafe manufacturer/codename: {value!r}")
    return value


def _ramdisk_roots(ramdisk_or_roots):
    if isinstance(ramdisk_or_roots, (str, Path)):
        return [Path(ramdisk_or_roots)]
    return [Path(root) for root in ramdisk_or_roots]


def detect_android_api(ramdisk_or_roots) -> Optional[int]:
    """Read stock SDK from one or more extracted ramdisk roots."""
    properties = {}
    for root in _ramdisk_roots(ramdisk_or_roots):
        for relpath in _PROPERTY_PATHS:
            path = root / relpath
            if not path.is_file():
                continue
            for line in path.read_text(
                    encoding="utf-8",
                    errors="replace").splitlines():
                if (
                        not line
                        or line.lstrip().startswith("#")
                        or "=" not in line):
                    continue
                key, val = line.split("=", 1)
                properties[key.strip()] = val.strip()
    for key in _API_KEYS:
        value = properties.get(key, "")
        if value.isdigit() and 1 <= int(value) <= 100:
            return int(value)
    return None


def find_recovery_fstab(ramdisk_or_roots) -> Optional[Path]:
    """Find recovery/fs_mgr fstab across ordered ramdisk roots."""
    preferred = (
        "etc/recovery.fstab",
        "system/etc/recovery.fstab",
        "vendor/etc/recovery.fstab",
        "recovery.fstab",
        "first_stage_ramdisk/recovery.fstab",
    )
    for root in _ramdisk_roots(ramdisk_or_roots):
        for relative in preferred:
            candidate = root / relative
            if candidate.is_file():
                return candidate
        for directory in (
                "first_stage_ramdisk",
                "vendor/etc",
                "odm/etc",
                "system/etc",
                "etc",
                "."):
            folder = root / directory
            if not folder.is_dir():
                continue
            for candidate in sorted(folder.glob("fstab.*")):
                if candidate.is_file():
                    return candidate
    return None


def resolve_skeleton(
        requested: str,
        api: Optional[int]) -> str:
    """Choose a template family; this is not a bootability claim."""
    if requested != "auto":
        return requested
    if api is None:
        return "omni"
    if api >= 34:
        return "twrp-14.1"
    if api >= 31:
        return "twrp-12.1"
    return "omni"


def choose_recovery_layout(
        requested: str,
        filename: str,
        is_ab: bool) -> str:
    if requested != "auto":
        return requested
    stem = Path(filename).stem.lower()
    if stem == "recovery":
        return "dedicated"
    if stem == "vendor_boot":
        return "vendor_boot"
    if stem == "boot" and is_ab:
        return "boot"
    return "unknown"


def normalize_partition_names(values: Iterable[str]):
    """Keep first safe partition occurrence."""
    seen = set()
    result = []
    for raw in values:
        if (
                not isinstance(raw, str)
                or not _PART.fullmatch(raw)):
            continue
        if raw not in seen:
            seen.add(raw)
            result.append(raw)
    return result


def valid_security_patch(value):
    """Return a real stock ISO security patch date, otherwise None."""
    if (
            not isinstance(value, str)
            or not _DATE.fullmatch(value)):
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    return value
