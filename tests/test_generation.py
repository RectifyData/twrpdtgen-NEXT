# SPDX-License-Identifier: Apache-2.0
"""Mocked end-to-end generation: validates templates without flashable images."""
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import patch

from twrpdtgen.next_support import NextOptions


class FakeBuildProp:
    def import_props(self, path):
        pass


class FakeDeviceInfo:
    def __init__(self, props):
        self.manufacturer = "samsung"
        self.codename = "beyond2lte"
        self.brand = "Samsung"
        self.model = "Galaxy S10+"
        self.gms_clientid_base = "android-samsung"
        self.build_description = "stock-user 14 valid release-keys"
        self.build_fingerprint = "samsung/beyond2lte:14/stock:user/release-keys"
        self.arch = Obj(arch="arm64", arch_variant="armv8-a", cpu_abi="arm64-v8a",
                        cpu_abi2="", bitness=64)
        self.second_arch = None
        self.cpu_variant = "generic"
        self.device_is_ab = False
        self.device_uses_updatable_apex = True
        self.bootloader_board_name = "beyond2lte"
        self.screen_density = 550
        self.use_vulkan = False
        self.device_uses_system_as_root = True
        self.device_uses_dynamic_partitions = True
        self.platform = "exynos9820"
        self.device_pixel_format = "RGBX_8888"
        self.vendor_build_security_patch = "2026-10-01"


class FakeFstab:
    def __init__(self, path):
        self.path = path

    def get_logical_partitions(self):
        return [Obj(src="system"), Obj(src="vendor"), Obj(src="system")]

    def get_ab_partitions_models(self):
        return []

    def format(self, twrp=False):
        return "/system ext4 /dev/block/mapper/system flags=logical\n"


def load_device_tree(image_info):
    class FakeAIK:
        def unpackimg(self, path):
            return image_info
        def cleanup(self):
            pass

    names = {
        "git": {"Repo": object},
        "sebaubuntu_libs": {},
        "sebaubuntu_libs.libaik": {"AIKManager": FakeAIK},
        "sebaubuntu_libs.libandroid": {},
        "sebaubuntu_libs.libandroid.device_info": {"DeviceInfo": FakeDeviceInfo},
        "sebaubuntu_libs.libandroid.fstab": {"Fstab": FakeFstab},
        "sebaubuntu_libs.libandroid.props": {"BuildProp": FakeBuildProp},
        "sebaubuntu_libs.liblogging": {"LOGD": lambda x: None},
    }
    fake_modules = {}
    for module_name, members in names.items():
        module = types.ModuleType(module_name)
        module.__dict__.update(members)
        fake_modules[module_name] = module
    with patch.dict(sys.modules, fake_modules):
        sys.modules.pop("twrpdtgen.device_tree", None)
        module = importlib.import_module("twrpdtgen.device_tree")
    return module.DeviceTree


class GenerationTests(unittest.TestCase):
    def test_modern_tree_render_and_safe_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            image = tmp / "recovery.img"
            image.write_bytes(b"stub-image")
            ramdisk = tmp / "ramdisk"
            (ramdisk / "etc").mkdir(parents=True)
            (ramdisk / "etc/recovery.fstab").write_text("# stock\n")
            (ramdisk / "prop.default").write_text("ro.build.version.sdk=34\n")
            (ramdisk / "system/bin").mkdir(parents=True)
            (ramdisk / "system/bin/recovery").write_text("stock recovery binary")
            (ramdisk / "init.rc").write_text("generic stock init")
            (ramdisk / "init.recovery.exynos9820.rc").write_text(
                "on init\n    setprop recovery.device 1\n")
            (ramdisk / "vendor/firmware").mkdir(parents=True)
            (ramdisk / "vendor/firmware/tsp.bin").write_bytes(b"firmware")
            kernel = tmp / "kernel"
            kernel.write_bytes(b"stub-kernel")
            image_info = Obj(ramdisk=ramdisk, kernel=kernel,
                             dt=None, dtb=None, dtbo=None,
                             header_version="3", base_address=None,
                             cmdline="console=null", pagesize=4096,
                             ramdisk_offset=None, tags_offset=None,
                             origsize=1024, ramdisk_compression="gzip",
                             sigtype="AVBv2")
            DeviceTree = load_device_tree(image_info)
            generator = DeviceTree(image)
            tree = generator.dump_to_folder(tmp / "output")
            self.assertTrue((tree / "twrp_beyond2lte.mk").is_file())
            self.assertTrue((tree / "proprietary-files.txt").is_file())
            self.assertIn(
                "No proprietary blob list can be inferred safely",
                (tree / "proprietary-files.txt").read_text(),
            )
            self.assertEqual(
                (tree / "recovery.stock.fstab").read_text(),
                "# stock\n",
            )
            self.assertFalse((tree / "omni_beyond2lte.mk").exists())
            self.assertFalse((tree / "vendorsetup.sh").exists())
            self.assertIn(
                "recovery/stock-root/",
                (tree / ".gitignore").read_text())
            self.assertEqual((tree / "prebuilt/kernel").read_bytes(), b"stub-kernel")
            self.assertIn("twrp-14.1", (tree / "README.md").read_text())
            # The complete stock ramdisk is preserved for audit/reuse, while
            # auto mode does not overwrite TWRP's own generic recovery/init.
            self.assertEqual(
                (tree / "recovery/stock-root/system/bin/recovery").read_text(),
                "stock recovery binary")
            self.assertEqual(
                (tree / "recovery/stock-root/init.rc").read_text(),
                "generic stock init")
            self.assertFalse((tree / "recovery/root/system/bin/recovery").exists())
            self.assertFalse((tree / "recovery/root/init.rc").exists())
            self.assertTrue(
                (tree / "recovery/root/init.recovery.exynos9820.rc").is_file())
            self.assertEqual(
                (tree / "recovery/root/vendor/firmware/tsp.bin").read_bytes(),
                b"firmware")
            manifest = (tree / "recovery/ramdisk-manifest.json").read_text()
            self.assertIn('"mode": "minimal"', manifest)
            self.assertIn('"kind": "dedicated_recovery"', manifest)
            board = (tree / "BoardConfig.mk").read_text()
            self.assertIn("TARGET_RECOVERY_FSTAB :=", board)
            self.assertIn("TARGET_USES_64_BIT_BINDER := true", board)
            self.assertIn("# Detected logical partitions: system vendor", board)
            self.assertNotIn("BOARD_SUPER_PARTITION_SIZE :=", board)
            self.assertNotIn("BOARD_RECOVERYIMAGE_PARTITION_SIZE :=", board)
            self.assertNotIn("2099-12-31", board)
            self.assertNotIn("--flags 3", board)
            self.assertNotIn("testkey_rsa4096", board)

            sentinel = tree / "keep.txt"
            sentinel.write_text("preserve")
            with self.assertRaises(FileExistsError):
                generator.dump_to_folder(tmp / "output")
            self.assertEqual(sentinel.read_text(), "preserve")
            generator.cleanup()

            options = NextOptions(
                skeleton="twrp-14.1", overwrite=True,
                super_size=9126805504, dynamic_group_size=9122611200,
                recovery_size=67108864)
            again = DeviceTree(image, options=options)
            again.dump_to_folder(tmp / "output")
            self.assertFalse(sentinel.exists())
            config = (tree / "BoardConfig.mk").read_text()
            self.assertEqual(config.count("system vendor"), 2)
            self.assertIn("BOARD_SUPER_PARTITION_SIZE := 9126805504", config)
            self.assertIn("BOARD_RECOVERYIMAGE_PARTITION_SIZE := 67108864", config)
            again.cleanup()


    def test_vendor_boot_recovery_fragment_selection_is_unambiguous(self):
        DeviceTree = load_device_tree(Obj())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            one = root / "one"
            two = root / "two"
            one.mkdir()
            two.mkdir()
            fragment_one = Obj(
                ramdisk_type=2, index=1, name="recovery-a",
                root=one, type_name="recovery", board_id=(1, 0))
            fragment_two = Obj(
                ramdisk_type=2, index=2, name="recovery-b",
                root=two, type_name="recovery", board_id=(2, 0))
            vendor = Obj(
                kind="vendor_boot", source=Path("vendor_boot.img"),
                vendor_ramdisk_fragments=[fragment_one],
                ramdisk_roots=[one])
            probe = object.__new__(DeviceTree)
            probe.modern_manager = object()
            probe.image_info = Obj(source_images=[vendor])
            probe.recovery_layout = "vendor_boot"
            probe.recovery_fragment = None
            roots, source = probe._select_recovery_ramdisk()
            self.assertEqual(roots, [one])
            self.assertEqual(
                source["kind"], "vendor_boot_recovery_fragment")
            self.assertEqual(source["fragment_name"], "recovery-a")

            vendor.vendor_ramdisk_fragments = [
                fragment_one, fragment_two]
            with self.assertRaisesRegex(
                    ValueError, "multiple RECOVERY fragments"):
                probe._select_recovery_ramdisk()

            probe.recovery_fragment = "2"
            roots, source = probe._select_recovery_ramdisk()
            self.assertEqual(roots, [two])
            self.assertEqual(source["fragment_name"], "recovery-b")


if __name__ == "__main__":
    unittest.main()
