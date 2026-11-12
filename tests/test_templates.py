# SPDX-License-Identifier: Apache-2.0
import unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from twrpdtgen.templates import render_template


class ProductTemplateTests(unittest.TestCase):
    def test_modern_product(self):
        device = Obj(codename="beyond2lte")
        out = render_template(None, "AndroidProducts.mk", to_file=False,
                              current_year="2026", product_prefix="twrp",
                              device_info=device)
        self.assertIn("twrp_beyond2lte.mk", out)
        self.assertNotIn("omni_beyond2lte.mk", out)

    def test_legacy_product(self):
        device = Obj(codename="beyond2lte")
        out = render_template(None, "AndroidProducts.mk", to_file=False,
                              current_year="2026", product_prefix="omni",
                              device_info=device)
        self.assertIn("omni_beyond2lte.mk", out)

    def test_board_does_not_spoof_sizes_or_patch(self):
        template = Path("twrpdtgen/templates/BoardConfig.mk.jinja2").read_text()
        self.assertNotIn("9126805504", template)
        self.assertNotIn("2099-12-31", template)
        self.assertNotIn("--flags 3", template)
        self.assertNotIn("testkey_rsa4096", template)


if __name__ == "__main__":
    unittest.main()
