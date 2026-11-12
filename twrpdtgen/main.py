#
# Copyright (C) 2026 The twrpdtgen-NEXT contributors
#
# SPDX-License-Identifier: Apache-2.0
#
"""Command-line interface for recovery device tree generation and extraction."""

from argparse import ArgumentParser
from pathlib import Path

from sebaubuntu_libs.liblogging import setup_logging
from twrpdtgen import __version__ as version, current_path
from twrpdtgen.next_support import (
    NextOptions,
    parse_partition_size,
)


def _add_image_arguments(parser):
    parser.add_argument(
        "image",
        type=Path,
        help=(
            "primary recovery, boot, init_boot, "
            "or vendor_boot image"))
    parser.add_argument(
        "--boot-image",
        type=Path,
        help="companion boot.img for split GKI layouts")
    parser.add_argument(
        "--vendor-boot",
        type=Path,
        help="companion vendor_boot.img (v3/v4)")
    parser.add_argument(
        "--init-boot",
        type=Path,
        help="companion init_boot.img (Android 13+)")


def _extract_only(args):
    from twrpdtgen.boot_image import ModernImageManager

    manager = ModernImageManager(
        args.image,
        boot_image=args.boot_image,
        vendor_boot=args.vendor_boot,
        init_boot=args.init_boot)
    try:
        info = manager.unpack()
        destination = manager.export(
            args.extract_only)
        print(
            f"Extracted {len(info.source_images)} "
            f"modern Android image(s) to {destination}")
        print(
            "manifest.json records header geometry, "
            "vendor ramdisk fragments and compression.")
    finally:
        manager.cleanup()


def main():
    print(
        "TWRP device tree generator NEXT\n"
        f"Version {version}\n")

    parser = ArgumentParser(
        prog="python3 -m twrpdtgen")
    _add_image_arguments(parser)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=current_path / "output",
        help="destination parent folder")
    parser.add_argument(
        "--extract-only",
        type=Path,
        metavar="DIR",
        help=(
            "only unpack modern boot/init_boot/vendor_boot "
            "components to DIR; do not generate a tree"))
    parser.add_argument(
        "--extract-to",
        type=Path,
        metavar="DIR",
        help=(
            "also preserve modern parsed components and "
            "expanded ramdisks in DIR"))
    parser.add_argument(
        "--skeleton",
        choices=(
            "auto",
            "omni",
            "twrp-12.1",
            "twrp-14.1"),
        default="auto",
        help=(
            "TWRP product skeleton; auto uses "
            "firmware SDK"))
    parser.add_argument(
        "--recovery-layout",
        choices=(
            "auto",
            "dedicated",
            "boot",
            "vendor_boot"),
        default="auto",
        help=(
            "override detected recovery storage location"))
    parser.add_argument(
        "--recovery-fragment",
        help=(
            "vendor_boot v4 RECOVERY fragment name or numeric index; "
            "required only when multiple recovery fragments exist"))
    parser.add_argument(
        "--recovery-root-mode",
        choices=("auto", "minimal", "full"),
        default="auto",
        help=(
            "how stock recovery files seed recovery/root: auto preserves the "
            "complete extracted ramdisk in stock-root and uses a conservative "
            "device overlay; full must be requested explicitly"))
    parser.add_argument(
        "--boot-size",
        type=parse_partition_size,
        help="verified boot partition size in bytes")
    parser.add_argument(
        "--recovery-size",
        type=parse_partition_size,
        help="verified recovery partition size in bytes")
    parser.add_argument(
        "--super-size",
        type=parse_partition_size,
        help="verified super partition size in bytes")
    parser.add_argument(
        "--dynamic-group-size",
        type=parse_partition_size,
        help="verified dynamic group size in bytes")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "explicitly delete an existing generated tree"))
    parser.add_argument(
        "--git",
        action="store_true",
        help=(
            "initialize and commit with your configured "
            "git identity"))
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true")
    args = parser.parse_args()
    setup_logging(args.debug)

    if args.extract_only:
        _extract_only(args)
        return

    options = NextOptions(
        skeleton=args.skeleton,
        recovery_layout=args.recovery_layout,
        recovery_root_mode=args.recovery_root_mode,
        boot_size=args.boot_size,
        recovery_size=args.recovery_size,
        super_size=args.super_size,
        dynamic_group_size=args.dynamic_group_size,
        overwrite=args.overwrite,
    )

    from twrpdtgen.device_tree import DeviceTree

    device_tree = DeviceTree(
        image=args.image,
        options=options,
        boot_image=args.boot_image,
        vendor_boot=args.vendor_boot,
        init_boot=args.init_boot,
        recovery_fragment=args.recovery_fragment)
    try:
        folder = device_tree.dump_to_folder(
            args.output,
            git=args.git)
        extracted = None
        if args.extract_to:
            extracted = (
                device_tree.export_image_components(
                    args.extract_to))
    finally:
        device_tree.cleanup()

    print(
        f"\nGenerated candidate tree at {folder}")
    if extracted is not None:
        print(
            f"Preserved parsed image components at "
            f"{extracted}")
    print(
        "Verify BoardConfig, fstab, AVB, encryption, "
        "ramdisk selection and partition layout before "
        "building or flashing.")


if __name__ == "__main__":
    main()
