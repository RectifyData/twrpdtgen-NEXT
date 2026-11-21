# SPDX-License-Identifier: Apache-2.0
"""Regression tests for Odin, Motorola and Pixel factory packages."""
import hashlib
import io
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from twrpdtgen.firmware_input import FirmwareInputError, prepare_firmware, _canonical_image
from twrpdtgen.tool_bootstrap import ToolInstallError


def image_zip(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return b.getvalue()


def sparse_fragment(raw_at, blocks=4, block_size=4096):
    """Model Motorola sparse fragment with a write at one absolute block."""
    payload = b'x' * block_size if raw_at == 0 else b'y' * block_size
    header = struct.pack('<IHHHHIIII', 0xED26FF3A, 1, 0, 28, 12, block_size, blocks, 3 if raw_at else 2, 0)
    chunks = []
    if raw_at:
        chunks.append(struct.pack('<HHII', 0xCAC3, 0, raw_at, 12))
    chunks.append(struct.pack('<HHII', 0xCAC1, 0, 1, 12 + len(payload)) + payload)
    chunks.append(struct.pack('<HHII', 0xCAC3, 0, blocks - raw_at - 1, 12))
    return header + b''.join(chunks)


class FirmwareInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_google_factory_outer_nested_image_zip(self):
        nested = image_zip({'boot.img': b'ANDROID!BOOT', 'vendor_boot.img': b'VNDRBOOT',
                            'init_boot.img': b'ANDROID!INIT', 'dtbo.img': b'DTBO'})
        factory = self.root / 'panther-factory-zip.zip'
        factory.write_bytes(image_zip({'panther/image-panther-123.zip': nested,
                                        'panther/flash-all.sh': b'no'}))
        with prepare_firmware(factory, allow_partial=True) as ready:
            self.assertEqual((ready.images / 'boot.img').read_bytes(), b'ANDROID!BOOT')
            self.assertTrue((ready.images / 'vendor_boot.img').exists())
            self.assertTrue((ready.images / 'init_boot.img').exists())
            self.assertTrue((ready.images / 'dtbo.img').exists())

    def test_samsung_ap_tar_md5_lz4_and_ext4_name(self):
        import lz4.frame
        package = self.root / 'AP_SMG975F.tar.md5'
        with tarfile.open(package, 'w') as tar:
            for name, payload in {'boot.img.lz4': b'ANDROID!BOOT',
                                  'recovery.img.lz4': b'ANDROID!RECOVERY',
                                  'vendor.img.ext4.lz4': b'fake-vendor'}.items():
                data = lz4.frame.compress(payload)
                item = tarfile.TarInfo(name)
                item.size = len(data)
                tar.addfile(item, io.BytesIO(data))
        package.write_bytes(package.read_bytes() + hashlib.md5(package.read_bytes()).hexdigest().encode())
        with prepare_firmware(package, allow_partial=True) as ready:
            self.assertEqual((ready.images / 'boot.img').read_bytes(), b'ANDROID!BOOT')
            self.assertEqual((ready.images / 'recovery.img').read_bytes(), b'ANDROID!RECOVERY')
            self.assertTrue((ready.images / 'vendor.img').exists())
            self.assertTrue(any('vendor:' in problem for problem in ready.blockers))

    def test_motorola_sparsechunks_are_overlaid_not_concatenated(self):
        package = self.root / 'moto_firmware.zip'
        package.write_bytes(image_zip({'boot.img': b'ANDROID!BOOT',
                                       'super.img_sparsechunk.0': sparse_fragment(0),
                                       'super.img_sparsechunk.1': sparse_fragment(1),
                                       'flashfile.xml': b'<xml />'}))
        # super contains fake bytes; isolate this test from any download attempt.
        with patch('twrpdtgen.firmware_input.find_lpunpack', side_effect=ToolInstallError('offline fixture')):
            with prepare_firmware(package, allow_partial=True) as ready:
                data = (ready.images / 'super.img').read_bytes()
            self.assertEqual(len(data), 4 * 4096)
            self.assertEqual(data[:4096], b'x' * 4096)
            self.assertEqual(data[4096:8192], b'y' * 4096)
            self.assertEqual(data[8192:], b'\x00' * 8192)

    def test_rejects_missing_motorola_sparsechunk(self):
        package = self.root / 'moto_missing.zip'
        package.write_bytes(image_zip({'boot.img': b'ANDROID!BOOT',
                                       'super.img_sparsechunk.0': sparse_fragment(0),
                                       'super.img_sparsechunk.2': sparse_fragment(1)}))
        with self.assertRaisesRegex(FirmwareInputError, 'Missing Motorola'):
            with prepare_firmware(package, allow_partial=True):
                pass

    def test_mixed_directory_boot_and_samsung_tar(self):
        (self.root / 'boot.img').write_bytes(b'ANDROID!BOOT')
        with tarfile.open(self.root / 'AP_FIRMWARE.tar', 'w') as tar:
            data = b'ANDROID!RECOVERY'
            member = tarfile.TarInfo('recovery.img')
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
        with prepare_firmware(self.root, allow_partial=True) as ready:
            self.assertTrue((ready.images / 'boot.img').exists())
            self.assertTrue((ready.images / 'recovery.img').exists())

    def test_zip_traversal_is_ignored(self):
        package = self.root / 'traversal.zip'
        package.write_bytes(image_zip({'../boot.img': b'EVIL', 'boot.img': b'ANDROID!SAFE'}))
        with prepare_firmware(package, allow_partial=True) as ready:
            self.assertEqual((ready.images / 'boot.img').read_bytes(), b'ANDROID!SAFE')
        self.assertFalse((self.root / 'boot.img').exists())

    def test_unknown_firmware_file_fails(self):
        p = self.root / 'firmware.rar'
        p.write_bytes(b'not-valid')
        with self.assertRaises(FirmwareInputError):
            with prepare_firmware(p):
                pass

    def test_reject_corrupt_samsung_md5_footer(self):
        package = self.root / 'AP_corrupt.tar.md5'
        with tarfile.open(package, 'w') as tar:
            data = b'ANDROID!BOOT'
            item = tarfile.TarInfo('boot.img')
            item.size = len(data)
            tar.addfile(item, io.BytesIO(data))
        package.write_bytes(package.read_bytes() + b'0' * 32)
        with self.assertRaisesRegex(FirmwareInputError, 'checksum mismatch'):
            with prepare_firmware(package):
                pass

    def test_tar_traversal_member_is_discarded(self):
        tar_path = self.root / 'AP_traversal.tar'
        with tarfile.open(tar_path, 'w') as tar:
            for name, data in [('../boot.img', b'EVIL'), ('boot.img', b'ANDROID!SAFE')]:
                item = tarfile.TarInfo(name)
                item.size = len(data)
                tar.addfile(item, io.BytesIO(data))
        with prepare_firmware(tar_path, allow_partial=True) as ready:
            self.assertEqual((ready.images / 'boot.img').read_bytes(), b'ANDROID!SAFE')
        self.assertFalse((self.root / 'boot.img').exists())

    def test_odin_ext4_basename_is_normalized(self):
        self.assertEqual(_canonical_image('images/vendor.img.ext4.lz4'), 'vendor.img')
        self.assertEqual(_canonical_image('system.img.ext4'), 'system.img')


if __name__ == '__main__':
    unittest.main()
