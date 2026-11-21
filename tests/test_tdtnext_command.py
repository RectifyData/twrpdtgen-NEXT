# SPDX-License-Identifier: Apache-2.0
"""Public tdtnext command interface and source-to-tree handoff regression tests."""
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

from twrpdtgen.main import build_parser
from twrpdtgen.tdtnext import run_firmware_job


class TdtNextCommandTests(unittest.TestCase):
    def test_parser_accepts_windows_like_firmware_and_output_paths(self):
        args = build_parser().parse_args([
            '--input', r'C:\Users\User\Downloads\AP_XYZ.tar.md5',
            '--output', r'D:\TWRP\output',
        ])
        self.assertEqual(str(args.input), r'C:\Users\User\Downloads\AP_XYZ.tar.md5')
        self.assertEqual(str(args.output), r'D:\TWRP\output')

    def test_source_to_tree_archives_audit_after_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'factory.zip'
            with zipfile.ZipFile(source, 'w') as zipfile_out:
                zipfile_out.writestr('boot.img', b'ANDROID!BOOT')
            dest = root / 'tree-output'
            calls = {}

            def generate(images_dir, target, archive, **kwargs):
                calls['input_image'] = (images_dir / 'boot.img').read_bytes()
                calls['options'] = kwargs
                target_tree = target / 'example' / 'device'
                target_tree.mkdir(parents=True)
                return None, target_tree, None

            def archive_tree(target_tree, path, **kwargs):
                calls['report_exists_at_archive_time'] = (target_tree / 'firmware-input-audit.json').is_file()
                path.write_bytes(b'test archive only')
                return path

            fake_auto = types.ModuleType('twrpdtgen.auto_tree')
            fake_auto.generate_from_directory = generate
            fake_archive = types.ModuleType('twrpdtgen.tree_archive')
            fake_archive.archive_tree = archive_tree
            with patch.dict(sys.modules, {'twrpdtgen.auto_tree': fake_auto,
                                          'twrpdtgen.tree_archive': fake_archive}):
                tree, archive = run_firmware_job(source, dest, allow_partial=True)
            self.assertEqual(calls['input_image'], b'ANDROID!BOOT')
            self.assertTrue(calls['report_exists_at_archive_time'])
            self.assertTrue(archive.is_file())
            self.assertIn('source_images', json.loads((tree / 'firmware-input-audit.json').read_text()))
            self.assertTrue(calls['options']['complete'])

    def test_cli_rejects_output_nested_in_firmware(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'boot.img').write_bytes(b'ANDROID!BOOT')
            with self.assertRaisesRegex(ValueError, 'inside its folder'):
                run_firmware_job(root, root / 'generated')

    def test_cli_rejects_same_input_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'boot.img').write_bytes(b'ANDROID!BOOT')
            with self.assertRaisesRegex(ValueError, 'Output must differ'):
                run_firmware_job(root, root)


if __name__ == '__main__':
    unittest.main()
