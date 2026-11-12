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


    def test_modern_board_uses_split_image_flags(self):
        device = Obj(
            manufacturer="google", codename="testdev",
            arch=Obj(arch="arm64", arch_variant="armv8-a",
                     cpu_abi="arm64-v8a", cpu_abi2="", bitness=64),
            cpu_variant="generic", second_arch=None,
            device_is_ab=True, device_uses_updatable_apex=True,
            bootloader_board_name="testdev", screen_density=420,
            use_vulkan=False, device_uses_system_as_root=True,
            device_uses_dynamic_partitions=False, platform="test",
            device_pixel_format="RGBX_8888")
        image = Obj(
            source_images=[Obj()], header_version="4",
            boot_header_version="4", init_boot_header_version="4",
            vendor_boot_header_version="4", base_address=0,
            kernel_offset=0x10008000, cmdline="generic",
            vendor_cmdline="vendor bootconfig", pagesize=4096,
            ramdisk_offset=0x11000000, tags_offset=0x10000100,
            dtb_offset=0x11F00000, dt=None, dtb=True, dtbo=None,
            kernel=True, bootconfig=True, ramdisk_compression="gzip",
            sigtype=None)
        options = Obj(
            boot_size=None, recovery_size=None,
            super_size=None, dynamic_group_size=None)
        out = render_template(
            None, "BoardConfig.mk", to_file=False,
            current_year="2026", skeleton="twrp-14.1",
            device_info=device, image_info=image,
            product_prefix="twrp", recovery_layout="vendor_boot",
            dynamic_partition_names=[], ab_partition_names=[],
            security_patch=None, next_options=options)
        self.assertIn("BOARD_BOOT_HEADER_VERSION := 4", out)
        self.assertIn("BOARD_INIT_BOOT_HEADER_VERSION := 4", out)
        self.assertIn("BOARD_VENDOR_BOOT_HEADER_VERSION := 4", out)
        self.assertIn("BOARD_USES_INIT_BOOT_IMAGE := true", out)
        self.assertIn("BOARD_USES_VENDOR_BOOTIMAGE := true", out)
        self.assertIn(
            "BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true", out)
        self.assertIn("BOARD_KERNEL_OFFSET := 268468224", out)
        self.assertIn("BOARD_VENDOR_CMDLINE := vendor bootconfig", out)
        self.assertIn(
            "BOARD_VENDOR_BOOTCONFIG := $(DEVICE_PATH)/prebuilt/bootconfig",
            out)
        self.assertNotIn("BOARD_BOOTIMG_HEADER_VERSION :=", out)

    def test_board_does_not_spoof_sizes_or_patch(self):
        template = Path("twrpdtgen/templates/BoardConfig.mk.jinja2").read_text()
        self.assertNotIn("9126805504", template)
        self.assertNotIn("2099-12-31", template)
        self.assertNotIn("--flags 3", template)
        self.assertNotIn("testkey_rsa4096", template)


if __name__ == "__main__":
    unittest.main()
