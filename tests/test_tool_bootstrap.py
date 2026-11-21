# SPDX-License-Identifier: Apache-2.0
"""Offline tests for safe on-demand lpunpack installation."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from twrpdtgen import tool_bootstrap as tools
from twrpdtgen.firmware_input import FirmwareInputError, PreparedFirmware, _unpack_super


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache_patch = patch.object(tools, '_cache_root', return_value=self.root)
        self.native_patch = patch.object(tools, '_local_lpunpack', return_value=None)
        self.cache_patch.start()
        self.native_patch.start()
        self.addCleanup(self.cache_patch.stop)
        self.addCleanup(self.native_patch.stop)

    def _install(self, command, **kwargs):
        self.assertNotIn('sudo', command)
        self.assertIn('--require-hashes', command)
        self.assertIn('--no-deps', command)
        self.assertIn('--target', command)
        staged = Path(command[command.index('--target') + 1])
        req = Path(command[-1]).read_text()
        self.assertIn(tools.LIBLP_WHEEL_SHA256, req)
        (staged / 'liblp/partition_tools').mkdir(parents=True)
        (staged / 'liblp/partition_tools/lpunpack.py').write_text('def main(): pass\n')
        return SimpleNamespace(returncode=0)

    def test_auto_installs_into_user_cache_and_reuses(self):
        with patch.object(tools.subprocess, 'run', side_effect=self._install) as proc:
            command, label = tools.find_lpunpack()
            self.assertIn('liblp-1.0.2', label)
            self.assertIn('-c', command)
            self.assertTrue((self.root / 'liblp-1.0.2/.tdtnext-installed').is_file())
            self.assertEqual(tools.find_lpunpack(), (command, label))
            self.assertEqual(proc.call_count, 1)

    def test_prefers_preinstalled_native_tool(self):
        with patch.object(tools, '_local_lpunpack', return_value=(['/usr/bin/lpunpack'], 'native')):
            with patch.object(tools.subprocess, 'run') as proc:
                self.assertEqual(tools.find_lpunpack(), (['/usr/bin/lpunpack'], 'native'))
                proc.assert_not_called()

    def test_respects_no_auto_install(self):
        with patch.object(tools.subprocess, 'run') as proc:
            with self.assertRaisesRegex(tools.ToolInstallError, 'disabled'):
                tools.find_lpunpack(auto_install=False)
            proc.assert_not_called()

    def test_failed_install_does_not_pollute_cache(self):
        with patch.object(tools.subprocess, 'run', return_value=SimpleNamespace(returncode=3)):
            with self.assertRaisesRegex(tools.ToolInstallError, 'pip exit 3'):
                tools.find_lpunpack()
        self.assertFalse((self.root / 'liblp-1.0.2/.tdtnext-installed').exists())

    def test_unpacked_super_uses_bootstrapped_command(self):
        src = self.root / 'super.img'
        src.write_bytes(b'not sparse test fixture')
        (self.root / 'scratch').mkdir()
        images = self.root / 'images'
        images.mkdir()
        ready = PreparedFirmware(images=images)
        args = []

        def fake_run(command, label):
            args.append(command)
            return ''

        with patch('twrpdtgen.firmware_input.find_lpunpack', return_value=(['python', '-c', 'test'], 'cached')), \
             patch('twrpdtgen.firmware_input._run_external', side_effect=fake_run):
            _unpack_super(src, self.root / 'scratch', ready, {}, auto_install=True)
        self.assertEqual(args[0][:3], ['python', '-c', 'test'])
        self.assertEqual(args[0][-2:], [src, self.root / 'scratch/logical'])
        self.assertEqual(ready.tools['lpunpack'], 'cached')

    def test_lpunpack_failure_is_actionable(self):
        src = self.root / 'super.img'
        src.write_bytes(b'test')
        ready = PreparedFirmware(images=self.root)
        with patch('twrpdtgen.firmware_input.find_lpunpack', side_effect=tools.ToolInstallError('No network')):
            with self.assertRaisesRegex(FirmwareInputError, 'No network'):
                _unpack_super(src, self.root / 'scratch', ready, {})


if __name__ == '__main__':
    unittest.main()
