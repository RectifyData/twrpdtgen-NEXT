# SPDX-License-Identifier: Apache-2.0
import gzip
import lz4.block
import lz4.frame
import zstandard
from pathlib import Path
import stat
import struct
import tempfile
import unittest

from twrpdtgen.boot_image import (
    ImageFormatError,
    ModernImageManager,
    RAMDISK_TYPE_RECOVERY,
    decompress_ramdisk,
    extract_newc,
    probe_image,
    unpack_modern_image,
)


def align(value, size):
    return (value + size - 1) // size * size


def newc(entries):
    out = bytearray()
    inode = 1
    for name, payload, mode in entries:
        if isinstance(payload, str):
            payload = payload.encode()
        encoded_name = name.encode() + b"\0"
        fields = [
            inode, mode, 0, 0, 1, 0, len(payload),
            0, 0, 0, 0, len(encoded_name), 0,
        ]
        out += b"070701" + b"".join(
            f"{value:08x}".encode() for value in fields)
        out += encoded_name
        out += b"\0" * ((-len(out)) % 4)
        out += payload
        out += b"\0" * ((-len(out)) % 4)
        inode += 1
    encoded_name = b"TRAILER!!!\0"
    fields = [
        inode, 0, 0, 0, 1, 0, 0,
        0, 0, 0, 0, len(encoded_name), 0,
    ]
    out += b"070701" + b"".join(
        f"{value:08x}".encode() for value in fields)
    out += encoded_name
    out += b"\0" * ((-len(out)) % 4)
    return bytes(out)


def boot_v4(ramdisk, destination, kernel=b"", signature=b""):
    header = bytearray(b"ANDROID!")
    header += struct.pack(
        "<4I", len(kernel), len(ramdisk), 0, 1584)
    header += struct.pack("<4I", 0, 0, 0, 0)
    header += struct.pack("<I", 4)
    header += (
        b"console=null"
        + b"\0" * (1536 - len(b"console=null")))
    header += struct.pack("<I", len(signature))
    assert len(header) == 1584
    image = bytearray(header)
    image += b"\0" * (4096 - len(image))
    image += kernel
    if kernel:
        image += b"\0" * (
            align(len(image), 4096) - len(image))
    image += ramdisk
    if signature:
        image += b"\0" * (
            align(len(image), 4096) - len(image))
        image += signature
    destination.write_bytes(image)


def vendor_boot_v4(
        fragments, destination,
        bootconfig=b"androidboot.test=1\n",
        dtb=b"DTB"):
    page = 4096
    header_size = 2128
    entry_size = 108
    section = bytearray()
    entries = []
    for index, (
            payload, ramdisk_type, name) in enumerate(fragments):
        offset = len(section)
        section += payload
        encoded_name = name.encode()
        entry = struct.pack(
            "<III", len(payload), offset, ramdisk_type)
        entry += (
            encoded_name
            + b"\0" * (32 - len(encoded_name)))
        entry += struct.pack(
            "<16I", *([index] + [0] * 15))
        assert len(entry) == entry_size
        entries.append(entry)
    table = b"".join(entries)
    cmdline = b"androidboot.hardware=test"
    header = bytearray(b"VNDRBOOT")
    header += struct.pack(
        "<5I", 4, page, 0x10008000,
        0x11000000, len(section))
    header += (
        cmdline + b"\0" * (2048 - len(cmdline)))
    header += struct.pack("<I", 0x10000100)
    name = b"testboard"
    header += name + b"\0" * (16 - len(name))
    header += struct.pack(
        "<IIQ", header_size, len(dtb), 0x11F00000)
    header += struct.pack(
        "<4I", len(table), len(entries),
        entry_size, len(bootconfig))
    assert len(header) == header_size
    image = bytearray(header)
    image += b"\0" * (
        align(len(image), page) - len(image))
    image += section
    image += b"\0" * (
        align(len(image), page) - len(image))
    image += dtb
    image += b"\0" * (
        align(len(image), page) - len(image))
    image += table
    image += b"\0" * (
        align(len(image), page) - len(image))
    image += bootconfig
    destination.write_bytes(image)


def vendor_boot_v3(
        ramdisk, destination, dtb=b"DTB3"):
    page = 4096
    header_size = 2112
    cmdline = b"androidboot.hardware=legacy"
    header = bytearray(b"VNDRBOOT")
    header += struct.pack(
        "<5I", 3, page, 0x10008000,
        0x11000000, len(ramdisk))
    header += (
        cmdline + b"\0" * (2048 - len(cmdline)))
    header += struct.pack("<I", 0x10000100)
    name = b"v3board"
    header += name + b"\0" * (16 - len(name))
    header += struct.pack(
        "<IIQ", header_size, len(dtb), 0x11F00000)
    assert len(header) == header_size
    image = bytearray(header)
    image += b"\0" * (
        align(len(image), page) - len(image))
    image += ramdisk
    image += b"\0" * (
        align(len(image), page) - len(image))
    image += dtb
    destination.write_bytes(image)


def legacy_lz4(payload):
    block = lz4.block.compress(
        payload, store_size=False)
    return (
        b"\x02\x21\x4c\x18"
        + struct.pack("<I", len(block))
        + block)


def frame_lz4(payload):
    return lz4.frame.compress(payload)


class ModernBootTests(unittest.TestCase):
    def setUp(self):
        self.cpio = newc([
            (
                "prop.default",
                "ro.build.version.sdk=35\n",
                stat.S_IFREG | 0o644),
            (
                "etc/recovery.fstab",
                "/system ext4 "
                "/dev/block/mapper/system "
                "flags=logical\n",
                stat.S_IFREG | 0o644),
        ])
        self.gzip_cpio = gzip.compress(self.cpio)

    def test_init_boot_v4_is_extracted(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            image = temp / "init_boot.img"
            boot_v4(self.gzip_cpio, image)
            self.assertEqual(probe_image(image)[1], 4)
            parsed = unpack_modern_image(
                image, temp / "out")
            self.assertEqual(parsed.kind, "init_boot")
            self.assertEqual(parsed.header_version, "4")
            self.assertEqual(
                parsed.ramdisk_compression, "gzip")
            self.assertTrue(
                (parsed.ramdisk / "prop.default").is_file())

    def test_vendor_boot_v4_fragments_bootconfig_and_dtb(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            platform = gzip.compress(newc([
                (
                    "vendor/default.prop",
                    "ro.product.vendor.device=test\n",
                    stat.S_IFREG | 0o644),
            ]))
            image = temp / "vendor_boot.img"
            vendor_boot_v4([
                (platform, 1, "platform"),
                (
                    self.gzip_cpio,
                    RAMDISK_TYPE_RECOVERY,
                    "recovery"),
            ], image)
            parsed = unpack_modern_image(
                image, temp / "out")
            self.assertEqual(
                parsed.product_name, "testboard")
            self.assertEqual(
                len(parsed.vendor_ramdisk_fragments), 2)
            self.assertEqual(
                parsed.vendor_ramdisk_fragments[1].type_name,
                "recovery")
            self.assertEqual(
                parsed.recovery_layout_hint, "vendor_boot")
            self.assertEqual(
                parsed.dtb.read_bytes(), b"DTB")
            self.assertEqual(
                parsed.bootconfig.read_bytes(),
                b"androidboot.test=1\n")
            self.assertTrue((
                parsed.recovery_ramdisk_roots[0]
                / "etc/recovery.fstab").is_file())

    def test_vendor_boot_v3_single_ramdisk(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            image = temp / "vendor_boot.img"
            vendor_boot_v3(
                self.gzip_cpio, image)
            parsed = unpack_modern_image(
                image, temp / "out")
            self.assertEqual(
                parsed.header_version, "3")
            self.assertEqual(
                parsed.product_name, "v3board")
            self.assertEqual(
                parsed.recovery_layout_hint, "vendor_boot")
            self.assertEqual(
                len(parsed.vendor_ramdisk_fragments), 1)
            self.assertEqual(
                parsed.vendor_ramdisk_fragments[0].type_name,
                "none")
            self.assertTrue(
                (parsed.ramdisk / "etc/recovery.fstab").is_file())
            self.assertEqual(
                parsed.dtb.read_bytes(), b"DTB3")

    def test_combines_init_boot_and_vendor_boot(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            init_boot = temp / "init_boot.img"
            vendor_boot = temp / "vendor_boot.img"
            boot_v4(self.gzip_cpio, init_boot)
            vendor_boot_v4([
                (
                    self.gzip_cpio,
                    RAMDISK_TYPE_RECOVERY,
                    "recovery"),
            ], vendor_boot)
            manager = ModernImageManager(
                init_boot, vendor_boot=vendor_boot)
            try:
                info = manager.unpack()
                self.assertEqual(
                    info.kind, "init_boot")
                self.assertEqual(
                    info.recovery_layout_hint,
                    "vendor_boot")
                self.assertEqual(
                    len(info.ramdisk_roots), 2)
                self.assertEqual(info.boot_header_version, "4")
                self.assertEqual(info.init_boot_header_version, "4")
                self.assertEqual(info.vendor_boot_header_version, "4")
                self.assertEqual(info.kernel_offset, 0x10008000)
                self.assertEqual(
                    info.vendor_cmdline,
                    "androidboot.hardware=test")
                manifest = manager.manifest()
                vendor = next(
                    image for image in manifest["images"]
                    if image["kind"] == "vendor_boot")
                self.assertEqual(
                    vendor["kernel_offset"], 0x10008000)
                self.assertEqual(
                    vendor["dtb_offset"], 0x11F00000)
                export = manager.export(
                    temp / "extracted")
                self.assertTrue(
                    (export / "manifest.json").is_file())
            finally:
                manager.cleanup()

    def test_zstd_ramdisk_is_native_python(self):
        compressed = zstandard.ZstdCompressor().compress(
            self.cpio)
        raw, kind = decompress_ramdisk(compressed)
        self.assertEqual(kind, "zstd")
        self.assertEqual(raw, self.cpio)

    def test_lz4_legacy_and_frame_ramdisks(self):
        legacy_raw, legacy_kind = decompress_ramdisk(
            legacy_lz4(self.cpio))
        frame_raw, frame_kind = decompress_ramdisk(
            frame_lz4(self.cpio))
        self.assertEqual(
            legacy_kind, "lz4_legacy")
        self.assertEqual(frame_kind, "lz4")
        self.assertEqual(legacy_raw, self.cpio)
        self.assertEqual(frame_raw, self.cpio)

    def test_cpio_path_traversal_is_rejected(self):
        archive = newc([
            (
                "../outside",
                b"x",
                stat.S_IFREG | 0o644),
        ])
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ImageFormatError):
                extract_newc(
                    archive, Path(temp) / "root")


if __name__ == "__main__":
    unittest.main()
