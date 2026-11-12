#
# Copyright (C) 2022 The Android Open Source Project
# Copyright (C) 2026 The twrpdtgen-NEXT contributors
#
# SPDX-License-Identifier: Apache-2.0
#

from datetime import datetime
import json
from git import Repo
from os import chmod
from pathlib import Path
from sebaubuntu_libs.libaik import AIKManager
from sebaubuntu_libs.libandroid.device_info import DeviceInfo
from sebaubuntu_libs.libandroid.fstab import Fstab
from sebaubuntu_libs.libandroid.props import BuildProp
from sebaubuntu_libs.liblogging import LOGD
from shutil import copyfile, rmtree
from stat import S_IRWXU, S_IRGRP, S_IROTH
from twrpdtgen import __version__ as version
from twrpdtgen.boot_image import (
    ModernImageManager,
    is_modern_boot_image,
)
from twrpdtgen.next_support import (
    NextOptions,
    choose_recovery_layout,
    detect_android_api,
    find_recovery_fstab,
    normalize_partition_names,
    resolve_skeleton,
    safe_component,
    valid_security_patch,
)
from twrpdtgen.templates import render_template


BUILDPROP_LOCATIONS = [
    Path("default.prop"),
    Path("prop.default"),
]
BUILDPROP_LOCATIONS += [
    Path(directory) / "build.prop"
    for directory in ("system", "vendor")
]
BUILDPROP_LOCATIONS += [
    Path(directory) / "etc" / "build.prop"
    for directory in ("system", "vendor")
]
BUILDPROP_LOCATIONS += [
    Path("first_stage_ramdisk/prop.default"),
    Path("system/system/build.prop"),
    Path("vendor/default.prop"),
]

INIT_RC_LOCATIONS = [Path()]
INIT_RC_LOCATIONS += [
    Path(directory) / "etc" / "init"
    for directory in ("system", "vendor")
]


class DeviceTree:
    """Build a conservative candidate TWRP device tree."""

    def __init__(
            self,
            image: Path,
            options: NextOptions = None,
            boot_image: Path = None,
            vendor_boot: Path = None,
            init_boot: Path = None):
        self.image = Path(image)
        self.options = options or NextOptions()
        self.current_year = str(datetime.now().year)
        self.aik_manager = None
        self.modern_manager = None

        if not self.image.is_file():
            raise FileNotFoundError(
                "Specified primary image doesn't exist")

        companions = (
            boot_image is not None
            or vendor_boot is not None
            or init_boot is not None)
        if companions or is_modern_boot_image(self.image):
            self.modern_manager = ModernImageManager(
                self.image,
                boot_image=boot_image,
                vendor_boot=vendor_boot,
                init_boot=init_boot)
            self.image_info = self.modern_manager.unpack()
            self.ramdisk_roots = list(
                self.image_info.ramdisk_roots)
            self.recovery_ramdisk_roots = list(
                self.image_info.recovery_ramdisk_roots)
        else:
            self.aik_manager = AIKManager()
            self.image_info = self.aik_manager.unpackimg(
                self.image)
            if not self.image_info.ramdisk:
                self.cleanup()
                raise ValueError(
                    "No ramdisk found in the supplied image")
            self.ramdisk_roots = [
                Path(self.image_info.ramdisk)]
            self.recovery_ramdisk_roots = list(
                self.ramdisk_roots)

        LOGD("Getting device infos...")
        self.build_prop = BuildProp()
        for root in self.ramdisk_roots:
            for location in BUILDPROP_LOCATIONS:
                build_prop = root / location
                if build_prop.is_file():
                    self.build_prop.import_props(
                        build_prop)

        self.device_info = DeviceInfo(self.build_prop)
        safe_component(self.device_info.manufacturer)
        safe_component(self.device_info.codename)

        self.android_api = detect_android_api(
            self.ramdisk_roots)
        self.skeleton = resolve_skeleton(
            self.options.skeleton,
            self.android_api)
        self.product_prefix = (
            "omni"
            if self.skeleton == "omni"
            else "twrp")

        detected_layout = getattr(
            self.image_info,
            "recovery_layout_hint",
            None)
        if (
                self.options.recovery_layout == "auto"
                and detected_layout):
            self.recovery_layout = detected_layout
        else:
            self.recovery_layout = choose_recovery_layout(
                self.options.recovery_layout,
                self.image.name,
                bool(self.device_info.device_is_ab))

        self.security_patch = valid_security_patch(
            getattr(
                self.device_info,
                "vendor_build_security_patch",
                None))

        fstab_roots = list(
            self.recovery_ramdisk_roots)
        fstab_roots += [
            root for root in self.ramdisk_roots
            if root not in fstab_roots
        ]
        fstab_location = find_recovery_fstab(
            fstab_roots)
        if fstab_location is None:
            raise ValueError(
                "No stock fstab found in extracted ramdisks")
        LOGD(
            f"Generating fstab using "
            f"{fstab_location} as reference...")
        self.fstab = Fstab(fstab_location)

        self.dynamic_partition_names = (
            normalize_partition_names(
                getattr(partition, "src", None)
                or getattr(partition, "name", None)
                for partition
                in self.fstab.get_logical_partitions()))
        self.ab_partition_names = (
            normalize_partition_names(
                getattr(partition, "name", None)
                or getattr(partition, "src", None)
                for partition
                in self.fstab.get_ab_partitions_models()))

        # Later ramdisk roots override same-named generic init scripts.
        init_scripts = {}
        for root in self.ramdisk_roots:
            for location in INIT_RC_LOCATIONS:
                init_path = root / location
                if not init_path.is_dir():
                    continue
                for init_rc in init_path.iterdir():
                    if (
                            init_rc.name.endswith(".rc")
                            and init_rc.name != "init.rc"):
                        init_scripts[init_rc.name] = init_rc
        self.init_rcs = list(init_scripts.values())

    def dump_to_folder(
            self,
            output_path: Path,
            git: bool = False) -> Path:
        parent = (
            Path(output_path)
            / self.device_info.manufacturer)
        if parent.is_symlink():
            raise ValueError(
                "Refusing to write under a "
                "symlinked manufacturer folder")
        device_tree_folder = (
            parent / self.device_info.codename)
        prebuilt_path = (
            device_tree_folder / "prebuilt")
        recovery_root_path = (
            device_tree_folder
            / "recovery"
            / "root")

        LOGD("Creating device tree folders...")
        if (
                device_tree_folder.exists()
                or device_tree_folder.is_symlink()):
            if not self.options.overwrite:
                raise FileExistsError(
                    f"{device_tree_folder} already exists; "
                    "pass --overwrite to replace it")
            if (
                    device_tree_folder.is_symlink()
                    or not device_tree_folder.is_dir()):
                raise ValueError(
                    "Refusing to overwrite a symlink "
                    "or non-directory")
            rmtree(device_tree_folder)
        device_tree_folder.mkdir(
            parents=True,
            exist_ok=False)
        prebuilt_path.mkdir(parents=True)
        recovery_root_path.mkdir(parents=True)

        LOGD("Writing makefiles/blueprints")
        self._render_template(
            device_tree_folder,
            "Android.bp",
            comment_prefix="//")
        self._render_template(
            device_tree_folder,
            "Android.mk")
        self._render_template(
            device_tree_folder,
            "AndroidProducts.mk")
        self._render_template(
            device_tree_folder,
            "BoardConfig.mk")
        self._render_template(
            device_tree_folder,
            "device.mk")
        self._render_template(
            device_tree_folder,
            "extract-files.sh")
        self._render_template(
            device_tree_folder,
            "omni_device.mk",
            out_file=(
                f"{self.product_prefix}_"
                f"{self.device_info.codename}.mk"))
        self._render_template(
            device_tree_folder,
            "README.md")
        self._render_template(
            device_tree_folder,
            "setup-makefiles.sh")
        if self.product_prefix == "omni":
            self._render_template(
                device_tree_folder,
                "vendorsetup.sh")

        chmod(
            device_tree_folder / "extract-files.sh",
            S_IRWXU | S_IRGRP | S_IROTH)
        chmod(
            device_tree_folder / "setup-makefiles.sh",
            S_IRWXU | S_IRGRP | S_IROTH)

        LOGD("Copying image components...")
        if self.image_info.kernel is not None:
            copyfile(
                self.image_info.kernel,
                prebuilt_path / "kernel")
        if self.image_info.dt is not None:
            copyfile(
                self.image_info.dt,
                prebuilt_path / "dt.img")
        if self.image_info.dtb is not None:
            copyfile(
                self.image_info.dtb,
                prebuilt_path / "dtb.img")
        if self.image_info.dtbo is not None:
            copyfile(
                self.image_info.dtbo,
                prebuilt_path / "dtbo.img")
        bootconfig = getattr(
            self.image_info,
            "bootconfig",
            None)
        if bootconfig is not None:
            copyfile(
                bootconfig,
                prebuilt_path / "bootconfig")

        if self.modern_manager is not None:
            (
                prebuilt_path
                / "image-metadata.json"
            ).write_text(
                json.dumps(
                    self.modern_manager.manifest(),
                    indent=2,
                    sort_keys=True) + "\n",
                encoding="utf-8")

        LOGD("Copying fstab...")
        (
            device_tree_folder
            / "recovery.fstab"
        ).write_text(
            self.fstab.format(twrp=True))

        LOGD("Copying init scripts...")
        for init_rc in self.init_rcs:
            copyfile(
                init_rc,
                recovery_root_path / init_rc.name,
                follow_symlinks=True)

        if not git:
            return device_tree_folder

        LOGD("Creating git repo...")
        git_repo = Repo.init(device_tree_folder)
        git_config_reader = (
            git_repo.config_reader())

        try:
            git_global_email = (
                git_config_reader.get_value(
                    "user", "email"))
            git_global_name = (
                git_config_reader.get_value(
                    "user", "name"))
        except Exception:
            git_global_email = None
            git_global_name = None

        if (
                git_global_email is None
                or git_global_name is None):
            raise RuntimeError(
                "--git requires git user.name and "
                "user.email; refusing to impersonate "
                "the upstream author")

        git_repo.index.add(["*"])
        commit_message = self._render_template(
            None,
            "commit_message",
            to_file=False)
        git_repo.index.commit(commit_message)
        return device_tree_folder

    def export_image_components(
            self,
            destination: Path) -> Path:
        if self.modern_manager is None:
            raise ValueError(
                "Persistent component export is available "
                "for modern boot/init_boot/vendor_boot "
                "inputs")
        return self.modern_manager.export(
            destination)

    def _render_template(
            self,
            *args,
            comment_prefix: str = "#",
            **kwargs):
        return render_template(
            *args,
            comment_prefix=comment_prefix,
            current_year=self.current_year,
            device_info=self.device_info,
            fstab=self.fstab,
            image_info=self.image_info,
            version=version,
            skeleton=self.skeleton,
            android_api=self.android_api,
            product_prefix=self.product_prefix,
            recovery_layout=self.recovery_layout,
            dynamic_partition_names=(
                self.dynamic_partition_names),
            ab_partition_names=(
                self.ab_partition_names),
            security_patch=self.security_patch,
            next_options=self.options,
            **kwargs)

    def cleanup(self):
        if self.modern_manager is not None:
            self.modern_manager.cleanup()
            self.modern_manager = None
        if self.aik_manager is not None:
            self.aik_manager.cleanup()
            self.aik_manager = None
