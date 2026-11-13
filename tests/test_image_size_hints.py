# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for source-derived size hints (not GPT geometry)."""
import tempfile
import unittest
from pathlib import Path

from twrpdtgen.next_support import image_partition_size_hint


class ImageSizeHintTests(unittest.TestCase):
    def test_4k_rounding_from_actual_file_length(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "recovery.img"
            image.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                image_partition_size_hint(image)
            for actual, expected in (
                    (1, 4096), (4096, 4096),
                    (4097, 8192), (8192, 8192),
                    (65537, 69632)):
                image.write_bytes(b"x" * actual)
                self.assertEqual(image_partition_size_hint(image), expected)


if __name__ == "__main__":
    unittest.main()
