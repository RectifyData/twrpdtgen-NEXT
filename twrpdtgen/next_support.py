#
# Copyright (C) 2026 The twrpdtgen-NEXT contributors
#
# SPDX-License-Identifier: Apache-2.0
#
"""Conservative skeleton and metadata choices for generated recovery trees."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import zlib
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
    """Parse verified partition sizes and reject invalid/unaligned geometry.

    Plain decimal and 0x-prefixed values are bytes. Binary KiB/MiB/GiB
    suffixes are accepted for the Colab/CLI convenience fields.
    """
    if isinstance(value, bool) or value is None:
        raise ValueError(
            "Partition size must be a byte count or KiB/MiB/GiB value")
    text = str(value).strip()
    match = re.fullmatch(
        r"(0[xX][0-9a-fA-F]+|[0-9]+)\s*(KiB|MiB|GiB)?",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise ValueError(
            "Partition size must be bytes or a KiB/MiB/GiB value")
    number, suffix = match.groups()
    try:
        base = 16 if number.lower().startswith("0x") else 10
        result = int(number, base)
    except ValueError as exc:
        raise ValueError("Invalid partition size") from exc

    if suffix:
        scale = {
            "kib": 1024,
            "mib": 1024 ** 2,
            "gib": 1024 ** 3,
        }[suffix.lower()]
        result *= scale

    if result <= 0 or result % 4096:
        raise ValueError(
            "Partition size must be positive and 4096-byte aligned")
    return result


@dataclass(frozen=True)
class NextOptions:
    skeleton: str = "auto"
    recovery_layout: str = "auto"
    recovery_root_mode: str = "auto"
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
        if self.recovery_root_mode not in (
                "auto", "minimal", "full"):
            raise ValueError("Unknown recovery root mode")
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


def detect_kernel_image_name(kernel: Path) -> str:
    """Infer the stock kernel artifact name from the extracted kernel bytes.

    This is deliberately content-based instead of guessing from device family.
    In particular, many legacy Android recovery images carry an Image.gz with
    one or more DTBs appended after the gzip stream.
    """
    if kernel is None:
        return "Image"
    kernel = Path(kernel)
    if not kernel.is_file():
        return "Image"

    with kernel.open("rb") as stream:
        magic = stream.read(4)
        stream.seek(0)
        if magic[:2] != b"\x1f\x8b":
            return "Image"

        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        appended = b""
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            decoder.decompress(chunk)
            if decoder.eof:
                appended = decoder.unused_data
                if len(appended) < 4:
                    appended += stream.read(4 - len(appended))
                break

    if appended.startswith(b"\xd0\x0d\xfe\xed"):
        return "Image.gz-dtb"
    return "Image.gz"


def format_twrp_fstab(fstab, *, system_as_root: bool = False) -> str:
    """Render a conservative TWRP fstab without discarding wipe geometry.

    sebaubuntu-libs' legacy TWRP formatter intentionally keeps only a small
    flag subset. Preserve the stock length= reservation because dropping it can
    overwrite footer metadata during a format. Logical/slotselect remain
    preserved as before. System-as-root '/' is exposed as /system_root, which
    is the conventional TWRP mount point for SAR devices.
    """
    entries = getattr(fstab, "entries", None)
    if entries is None:
        return fstab.format(twrp=True)

    rendered = []
    for entry in entries:
        original_mount = entry.mount_point
        mount_point = (
            "/system_root"
            if system_as_root and original_mount == "/"
            else original_mount
        )
        if original_mount == "/" and system_as_root:
            display = "System"
        else:
            display = Path(mount_point).name or "Root"

        flags = [f'display="{display}"']
        for flag in getattr(entry, "fs_flags", []):
            if flag in ("logical", "slotselect", "wait"):
                flags.append(flag)
            elif flag.startswith("length="):
                flags.append(flag)

        rendered.append(
            f"{mount_point} {entry.fs_type} {entry.src} "
            f"flags={';'.join(flags)}"
        )

    return "\n".join(rendered) + "\n"


def _is_display_brightness_path(path: str) -> bool:
    """Return true only for sysfs nodes that are clearly display backlights."""
    if re.fullmatch(
            r"/sys/class/backlight/[^/]+/brightness",
            path):
        return True
    return bool(re.fullmatch(
        r"/sys/class/leds/[^/]*(?:lcd|panel|backlight)[^/]*/brightness",
        path,
        flags=re.IGNORECASE,
    ))


def detect_brightness_policy(ramdisk_or_roots):
    """Infer recovery brightness settings from explicit stock init writes.

    The path is emitted only when one brightness node is unambiguous across the
    selected recovery payload. A default value is emitted only when startup
    actions (early-init/init/boot) agree on one positive numeric value. Writes
    from shutdown or property-triggered actions never become defaults.
    """
    matches = []
    pattern = re.compile(
        r"^\s*write\s+(\S*/brightness)\s+(\d+)\s*(?:#.*)?$"
    )
    trigger_pattern = re.compile(r"^\s*on\s+(.+?)\s*$")
    startup_triggers = {"early-init", "init", "boot"}

    for root in _ramdisk_roots(ramdisk_or_roots):
        candidates = list(root.glob("init*.rc"))
        for relative in (
                "system/etc/init",
                "vendor/etc/init",
                "odm/etc/init"):
            folder = root / relative
            if folder.is_dir():
                candidates.extend(folder.rglob("*.rc"))

        seen = set()
        for path in candidates:
            path = Path(path)
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            current_trigger = None
            for line in path.read_text(
                    encoding="utf-8",
                    errors="replace").splitlines():
                trigger = trigger_pattern.match(line)
                if trigger:
                    current_trigger = trigger.group(1).strip()
                    continue
                match = pattern.match(line)
                if not match:
                    continue
                brightness_path, raw_value = match.groups()
                if not _is_display_brightness_path(brightness_path):
                    continue
                matches.append((
                    brightness_path,
                    int(raw_value),
                    current_trigger,
                ))

    unique_paths = {path for path, _, _ in matches}
    if len(unique_paths) != 1:
        return None, None

    path = next(iter(unique_paths))
    startup_values = {
        value
        for candidate, value, trigger in matches
        if (
            candidate == path
            and trigger in startup_triggers
            and value > 0
        )
    }
    default = next(iter(startup_values)) if len(startup_values) == 1 else None
    return path, default

