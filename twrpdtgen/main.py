#
# Copyright (C) 2026 The twrpdtgen-NEXT contributors
#
# SPDX-License-Identifier: Apache-2.0
#
"""Command-line interface for recovery device tree generation."""

from argparse import ArgumentParser
from pathlib import Path

from sebaubuntu_libs.liblogging import setup_logging
from twrpdtgen import __version__ as version, current_path
from twrpdtgen.next_support import NextOptions, parse_partition_size


def main():
    print(f"TWRP device tree generator NEXT\nVersion {version}\n")
    parser = ArgumentParser(prog="python3 -m twrpdtgen")
    parser.add_argument(
        "image", type=Path,
        help="stock recovery/boot image containing a ramdisk (not standalone GKI vendor_boot)"
    )
    parser.add_argument("-o", "--output", type=Path, default=current_path / "output",
                        help="destination parent folder")
    parser.add_argument("--skeleton",
                        choices=("auto", "omni", "twrp-12.1", "twrp-14.1"),
                        default="auto",
                        help="TWRP product skeleton (auto uses firmware SDK, not host SDK)")
    parser.add_argument("--recovery-layout",
                        choices=("auto", "dedicated", "boot", "vendor_boot"),
                        default="auto",
                        help="explicit recovery storage location when known")
    parser.add_argument("--boot-size", type=parse_partition_size,
                        help="verified boot partition size in bytes")
    parser.add_argument("--recovery-size", type=parse_partition_size,
                        help="verified recovery partition size in bytes")
    parser.add_argument("--super-size", type=parse_partition_size,
                        help="verified super partition size in bytes")
    parser.add_argument("--dynamic-group-size", type=parse_partition_size,
                        help="verified dynamic group size in bytes")
    parser.add_argument("--overwrite", action="store_true",
                        help="explicitly delete an existing generated tree")
    parser.add_argument("--git", action="store_true",
                        help="initialize and commit with your configured git identity")
    parser.add_argument("-d", "--debug", action="store_true")
    args = parser.parse_args()
    setup_logging(args.debug)

    options = NextOptions(
        skeleton=args.skeleton,
        recovery_layout=args.recovery_layout,
        boot_size=args.boot_size,
        recovery_size=args.recovery_size,
        super_size=args.super_size,
        dynamic_group_size=args.dynamic_group_size,
        overwrite=args.overwrite,
    )
    # Imported here so --help and pure option tests work without image tooling.
    from twrpdtgen.device_tree import DeviceTree

    device_tree = DeviceTree(image=args.image, options=options)
    try:
        folder = device_tree.dump_to_folder(args.output, git=args.git)
    finally:
        device_tree.cleanup()
    print(f"\nGenerated candidate tree at {folder}")
    print("Verify the generated BoardConfig, fstabs, AVB and partition layout before building/flashing.")


if __name__ == "__main__":
    main()
