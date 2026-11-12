# Copyright (C) 2026 The twrpdtgen-NEXT contributors
# SPDX-License-Identifier: Apache-2.0
"""AOSP boot v3/v4, init_boot and vendor_boot v3/v4 extraction."""

from dataclasses import dataclass, field
import bz2
import gzip
import json
import lzma
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import tempfile
from typing import List, Optional, Tuple

import lz4.block
import lz4.frame

ANDROID_MAGIC = b"ANDROID!"
VENDOR_BOOT_MAGIC = b"VNDRBOOT"
BOOT_PAGE_SIZE = 4096
BOOT_HEADER_SIZE = {3: 1580, 4: 1584}
VENDOR_HEADER_SIZE = {3: 2112, 4: 2128}
VENDOR_ENTRY_SIZE = 108
MAX_RAMDISK_BYTES = 512 * 1024 * 1024
MAX_COMPONENT_BYTES = 1024 * 1024 * 1024

RAMDISK_TYPE_NONE = 0
RAMDISK_TYPE_PLATFORM = 1
RAMDISK_TYPE_RECOVERY = 2
RAMDISK_TYPE_DLKM = 3

LZ4_FRAME_MAGIC = b"\x04\x22\x4d\x18"
LZ4_LEGACY_MAGIC = b"\x02\x21\x4c\x18"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


class ImageFormatError(ValueError):
    """Raised when Android boot image geometry or ramdisk data is invalid."""


@dataclass(frozen=True)
class VendorRamdiskFragment:
    index: int
    size: int
    offset: int
    ramdisk_type: int
    name: str
    board_id: Tuple[int, ...]
    raw_path: Path
    root: Path
    compression: str

    @property
    def type_name(self):
        return {
            RAMDISK_TYPE_NONE: "none",
            RAMDISK_TYPE_PLATFORM: "platform",
            RAMDISK_TYPE_RECOVERY: "recovery",
            RAMDISK_TYPE_DLKM: "dlkm",
        }.get(self.ramdisk_type, f"unknown-{self.ramdisk_type}")


@dataclass
class ParsedImage:
    source: Path
    kind: str
    header_version: str
    boot_header_version: Optional[str]
    init_boot_header_version: Optional[str]
    vendor_boot_header_version: Optional[str]
    pagesize: int
    origsize: int
    ramdisk: Optional[Path] = None
    ramdisk_roots: List[Path] = field(default_factory=list)
    recovery_ramdisk_roots: List[Path] = field(default_factory=list)
    kernel: Optional[Path] = None
    dt: Optional[Path] = None
    dtb: Optional[Path] = None
    dtbo: Optional[Path] = None
    bootconfig: Optional[Path] = None
    base_address: Optional[int] = None
    kernel_offset: Optional[int] = None
    cmdline: str = ""
    ramdisk_offset: Optional[int] = None
    tags_offset: Optional[int] = None
    dtb_offset: Optional[int] = None
    ramdisk_compression: str = "unknown"
    sigtype: Optional[str] = None
    product_name: str = ""
    vendor_ramdisk_fragments: List[VendorRamdiskFragment] = field(default_factory=list)
    recovery_layout_hint: Optional[str] = None


@dataclass
class CombinedImageInfo:
    """Compatibility view consumed by the existing device-tree templates."""

    source_images: List[ParsedImage]
    primary: ParsedImage
    ramdisk_roots: List[Path]
    recovery_ramdisk_roots: List[Path]
    ramdisk: Path
    kernel: Optional[Path]
    dt: Optional[Path]
    dtb: Optional[Path]
    dtbo: Optional[Path]
    bootconfig: Optional[Path]
    header_version: str
    pagesize: int
    origsize: int
    base_address: Optional[int]
    kernel_offset: Optional[int]
    cmdline: str
    vendor_cmdline: str
    ramdisk_offset: Optional[int]
    tags_offset: Optional[int]
    dtb_offset: Optional[int]
    ramdisk_compression: str
    sigtype: Optional[str]
    kind: str
    product_name: str
    vendor_ramdisk_fragments: List[VendorRamdiskFragment]
    recovery_layout_hint: Optional[str]


def _align(value, alignment):
    if alignment <= 0:
        raise ImageFormatError("Invalid alignment")
    return (value + alignment - 1) // alignment * alignment


def _read_exact(handle, size):
    data = handle.read(size)
    if len(data) != size:
        raise ImageFormatError("Truncated Android boot image")
    return data


def _cstr(data):
    return data.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def probe_image(path):
    """Return boot magic and header version without unpacking."""
    path = Path(path)
    with path.open("rb") as image:
        magic = image.read(8)
        if magic == VENDOR_BOOT_MAGIC:
            return magic, struct.unpack("<I", _read_exact(image, 4))[0]
        if magic == ANDROID_MAGIC:
            image.seek(40)
            return magic, struct.unpack("<I", _read_exact(image, 4))[0]
    return magic, None


def is_modern_boot_image(path):
    magic, version = probe_image(path)
    return magic == VENDOR_BOOT_MAGIC or (
        magic == ANDROID_MAGIC and version in BOOT_HEADER_SIZE)


def _extract_component(image, offset, size, destination, image_size):
    if size < 0 or size > MAX_COMPONENT_BYTES or offset < 0 or offset + size > image_size:
        raise ImageFormatError("Image component exceeds validated image bounds")
    image.seek(offset)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_read_exact(image, size))


def _lz4_legacy(data):
    """Decode the legacy 8 MiB-block LZ4 format used by Android ramdisks."""
    pos = 4
    output = bytearray()
    while pos < len(data):
        if pos + 4 > len(data):
            raise ImageFormatError("Truncated LZ4 legacy block")
        size = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if size == 0:
            break
        if size > 8 * 1024 * 1024 or pos + size > len(data):
            raise ImageFormatError("Invalid LZ4 legacy block size")
        block = data[pos:pos + size]
        pos += size
        try:
            decoded = lz4.block.decompress(
                block,
                uncompressed_size=min(
                    8 * 1024 * 1024, MAX_RAMDISK_BYTES - len(output)))
        except lz4.block.LZ4BlockError as exc:
            raise ImageFormatError(f"Invalid LZ4 legacy block: {exc}") from exc
        output.extend(decoded)
        if len(output) > MAX_RAMDISK_BYTES:
            raise ImageFormatError("Ramdisk exceeds extraction safety limit")
    return bytes(output)


def decompress_ramdisk(data):
    """Decode common Android ramdisk formats and return newc bytes + format."""
    if len(data) > MAX_COMPONENT_BYTES:
        raise ImageFormatError("Ramdisk component exceeds safety limit")
    try:
        if data.startswith((b"070701", b"070702")):
            raw, kind = data, "cpio"
        elif data.startswith(b"\x1f\x8b"):
            raw, kind = gzip.decompress(data), "gzip"
        elif data.startswith(b"BZh"):
            raw, kind = bz2.decompress(data), "bzip2"
        elif data.startswith(b"\xfd7zXZ\x00"):
            raw, kind = lzma.decompress(data), "xz"
        elif data.startswith(LZ4_LEGACY_MAGIC):
            raw, kind = _lz4_legacy(data), "lz4_legacy"
        elif data.startswith(LZ4_FRAME_MAGIC):
            raw, kind = lz4.frame.decompress(data), "lz4"
        elif data.startswith(ZSTD_MAGIC):
            executable = shutil.which("zstd")
            if executable is None:
                raise ImageFormatError(
                    "Zstandard ramdisk detected; install the zstd command")
            # Feed zstd from a regular file rather than a stdin pipe. This lets
            # us cap stdout while zstd reads independently, avoiding a pipe
            # deadlock and preventing unbounded in-memory decompression.
            with tempfile.TemporaryDirectory(
                    prefix="twrpdtgen-zstd-") as temporary:
                compressed = Path(temporary) / "ramdisk.zst"
                compressed.write_bytes(data)
                process = subprocess.Popen(
                    [executable, "-q", "-d", "-c", str(compressed)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL)
                assert process.stdout is not None
                raw = process.stdout.read(MAX_RAMDISK_BYTES + 1)
                if len(raw) > MAX_RAMDISK_BYTES:
                    process.kill()
                    process.wait()
                    raise ImageFormatError(
                        "Ramdisk exceeds extraction safety limit")
                if process.wait() != 0:
                    raise ImageFormatError(
                        "zstd failed to decompress ramdisk")
            kind = "zstd"
        else:
            raw, kind = lzma.decompress(data, format=lzma.FORMAT_ALONE), "lzma"
    except (OSError, EOFError, lzma.LZMAError, lz4.frame.LZ4FrameError) as exc:
        raise ImageFormatError(f"Unable to decompress ramdisk: {exc}") from exc
    if len(raw) > MAX_RAMDISK_BYTES:
        raise ImageFormatError("Ramdisk exceeds extraction safety limit")
    if not raw.startswith((b"070701", b"070702")):
        raise ImageFormatError(
            f"Decoded {kind} ramdisk is not a newc CPIO archive")
    return raw, kind


def _safe_archive_path(root, name):
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts:
        raise ImageFormatError(f"Unsafe CPIO path: {name!r}")
    parts = [part for part in pure.parts if part not in ("", ".")]
    return root.joinpath(*parts) if parts else None


def extract_newc(data, root):
    """Safely materialize newc/crc CPIO without creating device nodes."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    pos = entries = 0
    while pos + 110 <= len(data):
        header = data[pos:pos + 110]
        pos += 110
        magic = header[:6]
        if magic not in (b"070701", b"070702"):
            raise ImageFormatError("Invalid newc CPIO header")
        try:
            fields = [
                int(header[6 + i * 8:14 + i * 8], 16)
                for i in range(13)
            ]
        except ValueError as exc:
            raise ImageFormatError("Invalid newc hexadecimal header") from exc
        mode, filesize, namesize = fields[1], fields[6], fields[11]
        if namesize <= 0 or namesize > 1024 * 1024:
            raise ImageFormatError("Invalid CPIO filename length")
        if filesize > MAX_RAMDISK_BYTES or pos + namesize > len(data):
            raise ImageFormatError("Invalid CPIO entry bounds")
        encoded_name = data[pos:pos + namesize]
        pos = _align(pos + namesize, 4)
        if not encoded_name.endswith(b"\0"):
            raise ImageFormatError("CPIO filename is not NUL-terminated")
        name = encoded_name[:-1].decode(
            "utf-8", errors="surrogateescape")
        if name == "TRAILER!!!":
            return
        if pos + filesize > len(data):
            raise ImageFormatError("Truncated CPIO payload")
        payload = data[pos:pos + filesize]
        pos = _align(pos + filesize, 4)
        if magic == b"070702" and (
                sum(payload) & 0xFFFFFFFF) != fields[12]:
            raise ImageFormatError("CPIO CRC mismatch")
        target = _safe_archive_path(root, name)
        if target is None:
            continue
        entries += 1
        if entries > 200000:
            raise ImageFormatError("CPIO contains too many entries")
        kind = mode & 0o170000
        if kind == 0o040000:
            target.mkdir(parents=True, exist_ok=True)
        elif kind == 0o100000:
            target.parent.mkdir(parents=True, exist_ok=True)
            cursor = root
            for part in target.relative_to(root).parts[:-1]:
                cursor /= part
                if cursor.is_symlink():
                    raise ImageFormatError(
                        "CPIO path traverses an archive symlink")
            if target.is_symlink():
                target.unlink()
            target.write_bytes(payload)
            try:
                target.chmod(mode & 0o7777)
            except OSError:
                pass
        elif kind == 0o120000:
            target.parent.mkdir(parents=True, exist_ok=True)
            link = PurePosixPath(
                payload.decode("utf-8", errors="surrogateescape"))
            if link.is_absolute() or ".." in link.parts:
                continue
            if target.exists() or target.is_symlink():
                target.unlink()
            try:
                target.symlink_to(str(link))
            except OSError:
                pass
        # Device nodes, sockets and FIFOs are intentionally not materialized.
    raise ImageFormatError("CPIO archive is missing TRAILER!!!")


def extract_ramdisk_archive(raw_path, root):
    raw, compression = decompress_ramdisk(Path(raw_path).read_bytes())
    extract_newc(raw, root)
    return compression


def _parse_boot(path, output):
    image_size = Path(path).stat().st_size
    with Path(path).open("rb") as image:
        if _read_exact(image, 8) != ANDROID_MAGIC:
            raise ImageFormatError("Not an Android boot/init_boot image")
        kernel_size, ramdisk_size, _os_version, header_size = struct.unpack(
            "<4I", _read_exact(image, 16))
        _read_exact(image, 16)
        version = struct.unpack("<I", _read_exact(image, 4))[0]
        if version not in BOOT_HEADER_SIZE or (
                header_size != BOOT_HEADER_SIZE[version]):
            raise ImageFormatError(
                f"Unsupported/invalid boot header v{version} "
                f"size {header_size}")
        cmdline = _cstr(_read_exact(image, 1536))
        signature_size = (
            struct.unpack("<I", _read_exact(image, 4))[0]
            if version == 4 else 0)
        kernel_offset = BOOT_PAGE_SIZE
        ramdisk_offset = (
            kernel_offset + _align(kernel_size, BOOT_PAGE_SIZE))
        if ramdisk_offset + ramdisk_size > image_size:
            raise ImageFormatError(
                "boot/init_boot ramdisk exceeds image bounds")
        signature_offset = (
            ramdisk_offset + _align(ramdisk_size, BOOT_PAGE_SIZE))
        if signature_size and (
                signature_offset + signature_size > image_size):
            raise ImageFormatError("boot signature exceeds image bounds")

        kernel = None
        if kernel_size:
            kernel = output / "kernel"
            _extract_component(
                image, kernel_offset, kernel_size, kernel, image_size)
        root = None
        compression = "none"
        if ramdisk_size:
            raw_ramdisk = output / "ramdisk"
            _extract_component(
                image, ramdisk_offset, ramdisk_size,
                raw_ramdisk, image_size)
            root = output / "ramdisk-root"
            compression = extract_ramdisk_archive(raw_ramdisk, root)
        if signature_size:
            _extract_component(
                image, signature_offset, signature_size,
                output / "boot_signature", image_size)

    stem = Path(path).stem.lower()
    if stem == "recovery":
        kind, hint = "recovery", "dedicated"
    elif stem == "init_boot" or (
            version == 4 and kernel_size == 0):
        kind, hint = "init_boot", None
    else:
        kind, hint = "boot", None
    roots = [root] if root else []
    return ParsedImage(
        Path(path), kind, str(version), BOOT_PAGE_SIZE, image_size,
        ramdisk=root, ramdisk_roots=roots,
        recovery_ramdisk_roots=roots if kind == "recovery" else [],
        kernel=kernel, cmdline=cmdline,
        ramdisk_compression=compression,
        recovery_layout_hint=hint)


def _parse_vendor_boot(path, output):
    image_size = Path(path).stat().st_size
    with Path(path).open("rb") as image:
        if _read_exact(image, 8) != VENDOR_BOOT_MAGIC:
            raise ImageFormatError("Not a vendor_boot image")
        version, page_size, kernel_addr, ramdisk_addr, ramdisk_size = (
            struct.unpack("<5I", _read_exact(image, 20)))
        if version not in VENDOR_HEADER_SIZE:
            raise ImageFormatError(
                f"Unsupported vendor_boot header v{version}")
        if page_size < 512 or page_size > 65536 or (
                page_size & (page_size - 1)):
            raise ImageFormatError(
                f"Invalid vendor_boot page size {page_size}")
        cmdline = _cstr(_read_exact(image, 2048))
        tags_addr = struct.unpack("<I", _read_exact(image, 4))[0]
        product_name = _cstr(_read_exact(image, 16))
        header_size, dtb_size = struct.unpack(
            "<2I", _read_exact(image, 8))
        dtb_addr = struct.unpack("<Q", _read_exact(image, 8))[0]
        if header_size != VENDOR_HEADER_SIZE[version]:
            raise ImageFormatError(
                f"Unexpected vendor_boot header size "
                f"{header_size} for v{version}")
        table_size = table_count = entry_size = bootconfig_size = 0
        if version == 4:
            table_size, table_count, entry_size, bootconfig_size = (
                struct.unpack("<4I", _read_exact(image, 16)))
            if table_count > 4096 or (
                    table_count and entry_size < VENDOR_ENTRY_SIZE) or (
                    table_count * entry_size > table_size):
                raise ImageFormatError(
                    "Invalid vendor ramdisk table geometry")

        ramdisk_base = _align(header_size, page_size)
        dtb_offset = (
            ramdisk_base + _align(ramdisk_size, page_size))
        table_offset = dtb_offset + _align(dtb_size, page_size)
        bootconfig_offset = (
            table_offset + _align(table_size, page_size))
        if version == 4 and bootconfig_size:
            required_end = bootconfig_offset + bootconfig_size
        elif version == 4 and table_size:
            required_end = table_offset + table_size
        else:
            required_end = dtb_offset + dtb_size
        if required_end > image_size:
            raise ImageFormatError(
                "vendor_boot sections exceed image bounds")

        dtb = None
        if dtb_size:
            dtb = output / "dtb"
            _extract_component(
                image, dtb_offset, dtb_size, dtb, image_size)
        bootconfig = None
        if bootconfig_size:
            bootconfig = output / "bootconfig"
            _extract_component(
                image, bootconfig_offset, bootconfig_size,
                bootconfig, image_size)

        fragments = []
        recovery_roots = []
        if version == 3:
            raw = output / "vendor_ramdisk"
            _extract_component(
                image, ramdisk_base, ramdisk_size, raw, image_size)
            root = output / "vendor_ramdisk-root"
            compression = extract_ramdisk_archive(raw, root)
            fragments.append(VendorRamdiskFragment(
                0, ramdisk_size, 0, RAMDISK_TYPE_NONE, "", tuple(),
                raw, root, compression))
        else:
            for index in range(table_count):
                image.seek(table_offset + index * entry_size)
                entry = _read_exact(image, entry_size)
                size, offset, ramdisk_type = struct.unpack_from(
                    "<3I", entry, 0)
                name = _cstr(entry[12:44])
                board_id = struct.unpack_from("<16I", entry, 44)
                if offset + size > ramdisk_size:
                    raise ImageFormatError(
                        "Vendor ramdisk fragment exceeds section bounds")
                raw = output / f"vendor_ramdisk{index:02d}"
                _extract_component(
                    image, ramdisk_base + offset, size,
                    raw, image_size)
                root = output / f"vendor_ramdisk{index:02d}-root"
                compression = extract_ramdisk_archive(raw, root)
                fragment = VendorRamdiskFragment(
                    index, size, offset, ramdisk_type, name,
                    tuple(board_id), raw, root, compression)
                fragments.append(fragment)
                if ramdisk_type == RAMDISK_TYPE_RECOVERY:
                    recovery_roots.append(root)

    ordered = sorted(
        fragments,
        key=lambda item: (
            item.ramdisk_type == RAMDISK_TYPE_RECOVERY,
            item.index))
    roots = [item.root for item in ordered]
    primary_root = (
        recovery_roots[0]
        if recovery_roots else (roots[0] if roots else None))
    return ParsedImage(
        Path(path), "vendor_boot", str(version),
        page_size, image_size,
        ramdisk=primary_root,
        ramdisk_roots=roots,
        recovery_ramdisk_roots=recovery_roots,
        dtb=dtb,
        bootconfig=bootconfig,
        base_address=0,
        kernel_offset=kernel_addr,
        cmdline=cmdline,
        ramdisk_offset=ramdisk_addr,
        tags_offset=tags_addr,
        dtb_offset=dtb_addr,
        ramdisk_compression=(
            ",".join(x.compression for x in fragments) or "none"),
        product_name=product_name,
        vendor_ramdisk_fragments=fragments,
        recovery_layout_hint=(
            "vendor_boot" if recovery_roots else None))


def unpack_modern_image(path, output):
    """Unpack boot/init_boot v3/v4 or vendor_boot v3/v4."""
    path, output = Path(path), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    magic, version = probe_image(path)
    if magic == VENDOR_BOOT_MAGIC:
        return _parse_vendor_boot(path, output)
    if magic == ANDROID_MAGIC and version in BOOT_HEADER_SIZE:
        return _parse_boot(path, output)
    raise ImageFormatError(
        "Expected boot/init_boot v3/v4 or vendor_boot v3/v4")


class ModernImageManager:
    """Combine modern boot image components into a generation input."""

    def __init__(
            self, primary, boot_image=None,
            vendor_boot=None, init_boot=None):
        self.primary = Path(primary)
        self.boot_image = (
            Path(boot_image) if boot_image else None)
        self.vendor_boot = (
            Path(vendor_boot) if vendor_boot else None)
        self.init_boot = (
            Path(init_boot) if init_boot else None)
        self._temporary = tempfile.TemporaryDirectory(
            prefix="twrpdtgen-next-")
        self.workspace = Path(self._temporary.name)
        self.parsed = []

    def _inputs(self):
        result, seen = [], set()
        for path in (
                self.primary, self.boot_image,
                self.vendor_boot, self.init_boot):
            if path is None:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            if not path.is_file():
                raise FileNotFoundError(
                    f"Image does not exist: {path}")
            seen.add(resolved)
            result.append(path)
        return result

    def unpack(self):
        self.parsed = [
            unpack_modern_image(
                path,
                self.workspace / f"{index:02d}-{path.stem}")
            for index, path in enumerate(self._inputs())
        ]
        if not self.parsed:
            raise ImageFormatError("No images supplied")
        by_kind = {}
        for item in self.parsed:
            if item.kind in by_kind:
                raise ImageFormatError(
                    f"Multiple {item.kind} images supplied")
            by_kind[item.kind] = item

        primary = self.parsed[0]
        vendor = by_kind.get("vendor_boot")
        boot = by_kind.get("boot") or by_kind.get("recovery")
        init_boot_image = by_kind.get("init_boot")
        boot_source = boot or init_boot_image or primary
        kernel = next(
            (item.kernel for item in self.parsed if item.kernel),
            None)
        generic_roots = []
        vendor_roots = []
        recovery_roots = []
        for item in self.parsed:
            if item.kind in ("boot", "init_boot"):
                generic_roots += item.ramdisk_roots
            elif item.kind == "recovery":
                recovery_roots += item.ramdisk_roots
            elif item.kind == "vendor_boot":
                vendor_roots += [
                    root for root in item.ramdisk_roots
                    if root not in item.recovery_ramdisk_roots]
                recovery_roots += item.recovery_ramdisk_roots
        roots = (
            generic_roots + vendor_roots + recovery_roots)
        if not roots:
            raise ImageFormatError(
                "No extractable ramdisk found in supplied images")
        address_source = vendor or boot_source
        layout_hint = (
            vendor.recovery_layout_hint
            if vendor and vendor.recovery_layout_hint
            else next(
                (item.recovery_layout_hint
                 for item in self.parsed
                 if item.recovery_layout_hint),
                None))
        return CombinedImageInfo(
            source_images=self.parsed,
            primary=primary,
            ramdisk_roots=roots,
            recovery_ramdisk_roots=recovery_roots,
            ramdisk=roots[-1],
            kernel=kernel,
            dt=None,
            dtb=vendor.dtb if vendor else None,
            dtbo=None,
            bootconfig=vendor.bootconfig if vendor else None,
            header_version=boot_source.header_version,
            boot_header_version=(
                boot.header_version if boot
                else (init_boot_image.header_version
                      if init_boot_image else None)),
            init_boot_header_version=(
                init_boot_image.header_version
                if init_boot_image else None),
            vendor_boot_header_version=(
                vendor.header_version if vendor else None),
            pagesize=(
                vendor.pagesize if vendor
                else boot_source.pagesize),
            origsize=primary.origsize,
            base_address=address_source.base_address,
            kernel_offset=address_source.kernel_offset,
            cmdline=boot_source.cmdline,
            vendor_cmdline=vendor.cmdline if vendor else "",
            ramdisk_offset=address_source.ramdisk_offset,
            tags_offset=address_source.tags_offset,
            dtb_offset=vendor.dtb_offset if vendor else None,
            ramdisk_compression=";".join(
                item.ramdisk_compression
                for item in self.parsed),
            sigtype=None,
            kind=primary.kind,
            product_name=vendor.product_name if vendor else "",
            vendor_ramdisk_fragments=(
                vendor.vendor_ramdisk_fragments if vendor else []),
            recovery_layout_hint=layout_hint)

    def manifest(self):
        return {
            "format": 1,
            "images": [{
                "file": item.source.name,
                "kind": item.kind,
                "header_version": int(item.header_version),
                "page_size": item.pagesize,
                "image_size": item.origsize,
                "cmdline": item.cmdline,
                "product_name": item.product_name,
                "base_address": item.base_address,
                "kernel_offset": item.kernel_offset,
                "ramdisk_offset": item.ramdisk_offset,
                "tags_offset": item.tags_offset,
                "dtb_offset": item.dtb_offset,
                "has_kernel": item.kernel is not None,
                "has_dtb": item.dtb is not None,
                "has_bootconfig": item.bootconfig is not None,
                "ramdisks": [{
                    "index": frag.index,
                    "size": frag.size,
                    "offset": frag.offset,
                    "type": frag.ramdisk_type,
                    "type_name": frag.type_name,
                    "name": frag.name,
                    "board_id": list(frag.board_id),
                    "compression": frag.compression,
                } for frag in item.vendor_ramdisk_fragments],
            } for item in self.parsed],
        }

    def export(self, destination):
        """Persist raw components, expanded ramdisks, and manifest."""
        destination = Path(destination)
        if destination.exists():
            raise FileExistsError(
                f"{destination} already exists")
        shutil.copytree(
            self.workspace, destination, symlinks=True)
        (destination / "manifest.json").write_text(
            json.dumps(
                self.manifest(),
                indent=2,
                sort_keys=True) + "\n",
            encoding="utf-8")
        return destination

    def cleanup(self):
        self._temporary.cleanup()
