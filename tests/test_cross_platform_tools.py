# SPDX-License-Identifier: Apache-2.0
"""Cross-platform dependency installation without actually modifying the host."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from twrpdtgen import tool_bootstrap as deps
from twrpdtgen import firmware_input


class CrossPlatformDependenciesTests(unittest.TestCase):
    def test_linux_installs_e2fsprogs_only_when_missing(self):
        with patch.object(deps, '_on_windows', return_value=False), \
             patch.object(deps, '_system_package_command', return_value=['sudo', 'apt-get', 'install', '-y', 'e2fsprogs']), \
             patch.object(deps.shutil, 'which', side_effect=[None, '/usr/bin/debugfs']), \
             patch.object(deps, '_run_visible') as installer:
            command, where, wsl = deps.find_extractor('debugfs')
        self.assertEqual(command, ['/usr/bin/debugfs'])
        self.assertFalse(wsl)
        installer.assert_called_once_with(['sudo', 'apt-get', 'install', '-y', 'e2fsprogs'], 'e2fsprogs')

    def test_does_not_install_when_native_tool_present(self):
        with patch.object(deps.shutil, 'which', return_value=r'C:\Tools\debugfs.exe'), \
             patch.object(deps, '_ensure_wsl') as wsl, \
             patch.object(deps, '_run_visible') as installer:
            result = deps.find_extractor('debugfs')
        self.assertEqual(result, ([r'C:\Tools\debugfs.exe'], r'C:\Tools\debugfs.exe', False))
        wsl.assert_not_called()
        installer.assert_not_called()

    def test_windows_reuses_wsl_and_installs_erofs_if_missing(self):
        with patch.object(deps, '_on_windows', return_value=True), \
             patch.object(deps.shutil, 'which', return_value=None), \
             patch.object(deps, '_ensure_wsl', return_value='wsl.exe'), \
             patch.object(deps, '_run_probe', side_effect=[False, True]), \
             patch.object(deps, '_wsl_package_install') as installer:
            cmd, label, via_wsl = deps.find_extractor('fsck.erofs')
        self.assertEqual(cmd, ['wsl.exe', '--exec', 'fsck.erofs'])
        self.assertTrue(via_wsl)
        installer.assert_called_once_with('wsl.exe', 'fsck.erofs')

    def test_existing_wsl_tool_works_when_autoinstall_disabled(self):
        with patch.object(deps, '_on_windows', return_value=True), \
             patch.object(deps.shutil, 'which', return_value=None), \
             patch.object(deps, '_ensure_wsl', return_value='wsl.exe'), \
             patch.object(deps, '_run_probe', return_value=True), \
             patch.object(deps, '_wsl_package_install') as installer:
            cmd, _, via_wsl = deps.find_extractor('debugfs', auto_install=False)
        self.assertTrue(via_wsl)
        self.assertEqual(cmd[-1], 'debugfs')
        installer.assert_not_called()

    def test_windows_missing_wsl_installer_is_visible_and_may_need_reboot(self):
        with patch.object(deps.shutil, 'which', return_value='wsl.exe'), \
             patch.object(deps, '_run_probe', side_effect=[False, False]), \
             patch.object(deps, '_run_visible') as visible:
            with self.assertRaisesRegex(deps.ToolInstallError, 'restart/first-run'):
                deps._ensure_wsl(auto_install=True)
        cmd, label = visible.call_args.args
        self.assertEqual(cmd[1:3], ['-NoProfile', '-Command'])
        self.assertIn('Start-Process', cmd[3])
        self.assertIn('-Verb RunAs', cmd[3])
        self.assertIn('Ubuntu', cmd[3])
        self.assertNotIn('Hidden', cmd[3])
        self.assertIn('administrator approval required', label)

    def test_linux_no_auto_install_does_not_run_installer(self):
        with patch.object(deps, '_on_windows', return_value=False), \
             patch.object(deps.shutil, 'which', return_value=None), \
             patch.object(deps, '_run_visible') as installer:
            with self.assertRaisesRegex(deps.ToolInstallError, 'no-auto-install'):
                deps.find_extractor('debugfs', auto_install=False)
        installer.assert_not_called()

    def test_wsl_windows_path_is_translated_safely(self):
        process = SimpleNamespace(stdout='/mnt/c/Users/Me/My Firmware/vendor.img\n',
                                  stderr='', returncode=0)
        with patch.object(deps.shutil, 'which', return_value='wsl.exe'), \
             patch.object(deps.subprocess, 'run', return_value=process) as run:
            output = deps.translated_path(Path('C:/Users/Me/My Firmware/vendor.img'), via_wsl=True)
        self.assertEqual(output, '/mnt/c/Users/Me/My Firmware/vendor.img')
        self.assertIn('wslpath', run.call_args.args[0])

    def test_liblp_python_uses_output_option_instead_of_positional(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / 'super.img'
            image.write_bytes(b'not sparse')
            prepared = firmware_input.PreparedFirmware(images=root)
            commands = []
            with patch.object(firmware_input, 'find_lpunpack', return_value=(['python', '-c', 'main'], 'Python liblp 1.0.2 (user cache)')), \
                 patch.object(firmware_input, '_run_external', side_effect=lambda cmd, *a: commands.append(cmd)):
                firmware_input._unpack_super(image, root, prepared, {})
            self.assertEqual(commands[0][-3:], [image, '-o', root / 'logical'])

    def test_parser_supports_setup_and_opt_out(self):
        from twrpdtgen.main import build_parser
        args = build_parser().parse_args(['--setup-tools', '--no-auto-install'])
        self.assertTrue(args.setup_tools)
        self.assertTrue(args.no_auto_install)


if __name__ == '__main__':
    unittest.main()
