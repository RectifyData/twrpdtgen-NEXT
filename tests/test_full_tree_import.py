# SPDX-License-Identifier: Apache-2.0
import tempfile
import unittest
from pathlib import Path
from twrpdtgen.full_tree import CompletionError, complete_tree


class FullTreeImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.tree = self.parent / 'tree'
        self.tree.mkdir()
        for name, data in {
            'AndroidProducts.mk': 'PRODUCT_MAKEFILES := $(LOCAL_DIR)/omni_test.mk\n',
            'BoardConfig.mk': 'ALLOW_MISSING_DEPENDENCIES := true\n',
            'device.mk': '# output\n',
            'recovery.fstab': '/system ext4 /dev/block/system\n',
            'omni_test.mk': '$(call inherit-product, device/sample/test/device.mk)\n',
        }.items():
            (self.tree / name).write_text(data)

    def test_vendor_dlkm_and_vendor_root_copy(self):
        vendor = self.parent / 'vendor'
        (vendor / 'etc/vintf').mkdir(parents=True)
        (vendor / 'etc/vintf/manifest.xml').write_text('<manifest/>')
        dlkm = self.parent / 'vendor_dlkm'
        (dlkm / 'lib/modules').mkdir(parents=True)
        (dlkm / 'lib/modules/touch.ko').write_bytes(b'MODULE')
        output = self.parent / 'completed'
        report = complete_tree(self.tree, output, partition_roots={
            'vendor': vendor, 'vendor_dlkm': dlkm})
        self.assertEqual((output / 'recovery/root/vendor/etc/vintf/manifest.xml').read_text(), '<manifest/>')
        self.assertEqual((output / 'recovery/root/vendor_dlkm/lib/modules/touch.ko').read_bytes(), b'MODULE')
        self.assertEqual(len(report['files']), 2)
        self.assertNotIn('ALLOW_MISSING_DEPENDENCIES := true', (output / 'BoardConfig.mk').read_text())

    def test_conflicting_vendor_source_fails_safely(self):
        stock = self.tree / 'recovery/stock-root/vendor/etc/vintf'
        stock.mkdir(parents=True)
        (stock / 'manifest.xml').write_bytes(b'OLD')
        vendor = self.parent / 'vendor'
        (vendor / 'etc/vintf').mkdir(parents=True)
        (vendor / 'etc/vintf/manifest.xml').write_bytes(b'NEW')
        output = self.parent / 'bad'
        with self.assertRaisesRegex(CompletionError, 'Conflicting'):
            complete_tree(self.tree, output, partition_roots={'vendor': vendor})
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
