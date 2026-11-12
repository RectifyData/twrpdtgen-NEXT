#
# Copyright (C) 2022 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

from datetime import datetime
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
from twrpdtgen.templates import render_template
from typing import List
from twrpdtgen.next_support import (NextOptions, choose_recovery_layout,
    detect_android_api, normalize_partition_names, resolve_skeleton,
    safe_component, valid_security_patch)

BUILDPROP_LOCATIONS = [Path() / "default.prop",
                       Path() / "prop.default",]
BUILDPROP_LOCATIONS += [Path() / dir / "build.prop"
                        for dir in ["system", "vendor"]]
BUILDPROP_LOCATIONS += [Path() / dir / "etc" / "build.prop"
                        for dir in ["system", "vendor"]]

FSTAB_LOCATIONS = [Path() / "etc" / "recovery.fstab"]
FSTAB_LOCATIONS += [Path() / dir / "etc" / "recovery.fstab"
                    for dir in ["system", "vendor"]]

INIT_RC_LOCATIONS = [Path()]
INIT_RC_LOCATIONS += [Path() / dir / "etc" / "init"
                      for dir in ["system", "vendor"]]

class DeviceTree:
	"""
	A class representing a device tree

	It initialize a basic device tree structure
	and save the location of some important files
	"""
	def __init__(self, image: Path, options: NextOptions = None):
		"""Initialize the device tree class."""
		self.image = Path(image)
		self.options = options or NextOptions()

		self.current_year = str(datetime.now().year)

		# Check if the image exists
		if not self.image.is_file():
			raise FileNotFoundError("Specified file doesn't exist")

		# Extract the image
		self.aik_manager = AIKManager()
		self.image_info = self.aik_manager.unpackimg(self.image)

		if not self.image_info.ramdisk:
			self.aik_manager.cleanup()
			raise ValueError("No ramdisk in the supplied image. GKI boot images may need vendor_boot/init_boot extraction; this generator does not yet unpack those standalone formats.")

		LOGD("Getting device infos...")
		self.build_prop = BuildProp()
		for build_prop in [self.image_info.ramdisk / location for location in BUILDPROP_LOCATIONS]:
			if not build_prop.is_file():
				continue

			self.build_prop.import_props(build_prop)

		self.device_info = DeviceInfo(self.build_prop)
		# Untrusted properties must never become an output-path traversal.
		safe_component(self.device_info.manufacturer)
		safe_component(self.device_info.codename)
		self.android_api = detect_android_api(self.image_info.ramdisk)
		self.skeleton = resolve_skeleton(self.options.skeleton, self.android_api)
		self.product_prefix = "omni" if self.skeleton == "omni" else "twrp"
		self.recovery_layout = choose_recovery_layout(
			self.options.recovery_layout, self.image.name,
			bool(self.device_info.device_is_ab))
		self.security_patch = valid_security_patch(
			getattr(self.device_info, "vendor_build_security_patch", None))

		# Generate fstab
		fstab = None
		for fstab_location in [self.image_info.ramdisk / location for location in FSTAB_LOCATIONS]:
			if not fstab_location.is_file():
				continue

			LOGD(f"Generating fstab using {fstab} as reference...")
			fstab = Fstab(fstab_location)
			break

		if fstab is None:
			raise AssertionError("fstab not found")

		self.fstab = fstab
		self.dynamic_partition_names = normalize_partition_names(
			getattr(p, "src", None) or getattr(p, "name", None)
			for p in fstab.get_logical_partitions())
		self.ab_partition_names = normalize_partition_names(
			getattr(p, "name", None) or getattr(p, "src", None)
			for p in fstab.get_ab_partitions_models())

		# Search for init rc files
		self.init_rcs: List[Path] = []
		for init_rc_path in [self.image_info.ramdisk / location for location in INIT_RC_LOCATIONS]:
			if not init_rc_path.is_dir():
				continue

			self.init_rcs += [init_rc for init_rc in init_rc_path.iterdir()
			                  if init_rc.name.endswith(".rc") and init_rc.name != "init.rc"]

	def dump_to_folder(self, output_path: Path, git: bool = False) -> Path:
		device_tree_folder = Path(output_path) / self.device_info.manufacturer / self.device_info.codename
		prebuilt_path = device_tree_folder / "prebuilt"
		recovery_root_path = device_tree_folder / "recovery" / "root"

		LOGD("Creating device tree folders...")
		if device_tree_folder.exists() or device_tree_folder.is_symlink():
			if not self.options.overwrite:
				raise FileExistsError(
					f"{device_tree_folder} already exists; pass --overwrite to replace it")
			if device_tree_folder.is_symlink() or not device_tree_folder.is_dir():
				raise ValueError("Refusing to overwrite a symlink or non-directory")
			rmtree(device_tree_folder)
		device_tree_folder.mkdir(parents=True, exist_ok=False)
		prebuilt_path.mkdir(parents=True)
		recovery_root_path.mkdir(parents=True)

		LOGD("Writing makefiles/blueprints")
		self._render_template(device_tree_folder, "Android.bp", comment_prefix="//")
		self._render_template(device_tree_folder, "Android.mk")
		self._render_template(device_tree_folder, "AndroidProducts.mk")
		self._render_template(device_tree_folder, "BoardConfig.mk")
		self._render_template(device_tree_folder, "device.mk")
		self._render_template(device_tree_folder, "extract-files.sh")
		self._render_template(device_tree_folder, "omni_device.mk",
		                      out_file=f"{self.product_prefix}_{self.device_info.codename}.mk")
		self._render_template(device_tree_folder, "README.md")
		self._render_template(device_tree_folder, "setup-makefiles.sh")
		if self.product_prefix == "omni":
			self._render_template(device_tree_folder, "vendorsetup.sh")

		# Set permissions
		chmod(device_tree_folder / "extract-files.sh", S_IRWXU | S_IRGRP | S_IROTH)
		chmod(device_tree_folder / "setup-makefiles.sh", S_IRWXU | S_IRGRP | S_IROTH)

		LOGD("Copying kernel...")
		if self.image_info.kernel is not None:
			copyfile(self.image_info.kernel, prebuilt_path / "kernel")
		if self.image_info.dt is not None:
			copyfile(self.image_info.dt, prebuilt_path / "dt.img")
		if self.image_info.dtb is not None:
			copyfile(self.image_info.dtb, prebuilt_path / "dtb.img")
		if self.image_info.dtbo is not None:
			copyfile(self.image_info.dtbo, prebuilt_path / "dtbo.img")

		LOGD("Copying fstab...")
		(device_tree_folder / "recovery.fstab").write_text(self.fstab.format(twrp=True))

		LOGD("Copying init scripts...")
		for init_rc in self.init_rcs:
			copyfile(init_rc, recovery_root_path / init_rc.name, follow_symlinks=True)

		if not git:
			return device_tree_folder

		# Create a git repo
		LOGD("Creating git repo...")

		git_repo = Repo.init(device_tree_folder)
		git_config_reader = git_repo.config_reader()

		try:
			git_global_email, git_global_name = git_config_reader.get_value('user', 'email'), git_config_reader.get_value('user', 'name')
		except Exception:
			git_global_email, git_global_name = None, None

		if git_global_email is None or git_global_name is None:
			raise RuntimeError("--git requires git user.name and user.email; refusing to impersonate the upstream author")

		git_repo.index.add(["*"])
		commit_message = self._render_template(None, "commit_message", to_file=False)
		git_repo.index.commit(commit_message)

		return device_tree_folder

	def _render_template(self, *args, comment_prefix: str = "#", **kwargs):
		return render_template(*args,
		                       comment_prefix=comment_prefix,
		                       current_year=self.current_year,
		                       device_info=self.device_info,
		                       fstab=self.fstab,
		                       image_info=self.image_info,
		                       version=version,
		                       skeleton=self.skeleton,
		                       product_prefix=self.product_prefix,
		                       recovery_layout=self.recovery_layout,
		                       dynamic_partition_names=self.dynamic_partition_names,
		                       ab_partition_names=self.ab_partition_names,
		                       security_patch=self.security_patch,
		                       next_options=self.options,
		                       **kwargs)

	def cleanup(self):
		# Cleanup
		self.aik_manager.cleanup()
