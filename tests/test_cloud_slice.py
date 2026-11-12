# SPDX-License-Identifier: Apache-2.0
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

import lz4.frame

from twrpdtgen.cloud_slice import (
    CloudSliceError,
    _host_asset_key,
    _package_kind,
    select_samloader_asset,
    slice_firmware,
)


def make_tar(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, payload in entries:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(payload))
    # Samsung .tar.md5 packages have checksum data after the TAR stream.
    return stream.getvalue() + b"0" * 32


def make_firmware(path, packages):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as bundle:
        for name, payload in packages:
            bundle.writestr(name, payload)


class CloudSliceTests(unittest.TestCase):
    def test_streams_only_requested_lz4_payload(self):
        raw = (b"boot-image-payload\0" * 8192)
        ap = make_tar([
            ("metadata.bin", b"not-this"),
            ("boot.img.lz4", lz4.frame.compress(raw)),
            ("vendor_boot.img.lz4", lz4.frame.compress(b"vendor")),
        ])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            firmware = root / "firmware.zip"
            output = root / "boot.img"
            make_firmware(
                firmware,
                [
                    ("BL_TEST.tar.md5", make_tar([("sboot.bin.lz4", lz4.frame.compress(b"bl"))])),
                    ("AP_TEST.tar.md5", ap),
                ],
            )
            result = slice_firmware(
                firmware,
                "boot",
                output=output,
            )
            self.assertEqual(output.read_bytes(), raw)
            self.assertEqual(result.package_member, "AP_TEST.tar.md5")
            self.assertEqual(result.payload_member, "boot.img.lz4")
            self.assertEqual(result.compression, "lz4")
            self.assertEqual(result.output_size, len(raw))
            self.assertEqual(len(result.sha256), 64)

    def test_raw_payload_is_copied_without_decompression(self):
        recovery = b"ANDROID!" + b"recovery" * 512
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            firmware = root / "firmware.zip"
            output = root / "recovery.img"
            make_firmware(
                firmware,
                [("AP_TEST.tar.md5", make_tar([("recovery.img", recovery)]))],
            )
            result = slice_firmware(
                firmware,
                "recovery.img",
                output=output,
            )
            self.assertEqual(output.read_bytes(), recovery)
            self.assertEqual(result.compression, "none")

    def test_package_filter_avoids_wrong_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            firmware = root / "firmware.zip"
            output = root / "modem.bin"
            make_firmware(
                firmware,
                [
                    ("AP_TEST.tar.md5", make_tar([("modem.bin", b"wrong")])),
                    ("CP_TEST.tar.md5", make_tar([("modem.bin", b"right")])),
                ],
            )
            result = slice_firmware(
                firmware,
                "modem",
                output=output,
                package="CP",
            )
            self.assertEqual(output.read_bytes(), b"right")
            self.assertEqual(result.package_member, "CP_TEST.tar.md5")

    def test_output_is_not_overwritten_without_opt_in(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            firmware = root / "firmware.zip"
            output = root / "boot.img"
            output.write_bytes(b"keep")
            make_firmware(
                firmware,
                [("AP_TEST.tar.md5", make_tar([("boot.img", b"new")]))],
            )
            with self.assertRaises(FileExistsError):
                slice_firmware(firmware, "boot", output=output)
            self.assertEqual(output.read_bytes(), b"keep")

    def test_missing_payload_has_clear_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            firmware = root / "firmware.zip"
            make_firmware(
                firmware,
                [("AP_TEST.tar.md5", make_tar([("recovery.img", b"x")]))],
            )
            with self.assertRaisesRegex(CloudSliceError, "was not found"):
                slice_firmware(firmware, "boot", output=root / "boot.img")

    def test_package_classification(self):
        self.assertEqual(_package_kind("AP_foo.tar.md5"), "AP")
        self.assertEqual(_package_kind("HOME_CSC_foo.tar.md5"), "HOME_CSC")
        self.assertEqual(_package_kind("CP_foo.tar.md5"), "CP")

    def test_release_asset_selection(self):
        release = {
            "assets": [
                {"name": "samloader-v2.2.0-linux-aarch64.zip"},
                {"name": "samloader-v2.2.0-linux-x86_64.zip"},
                {"name": "samloader-v2.2.0-windows-x86_64.zip"},
            ]
        }
        asset = select_samloader_asset(
            release,
            system="Linux",
            machine="AMD64",
        )
        self.assertEqual(
            asset["name"],
            "samloader-v2.2.0-linux-x86_64.zip",
        )
        self.assertEqual(
            _host_asset_key("Windows", "x86_64"),
            "windows-x86_64",
        )


if __name__ == "__main__":
    unittest.main()
