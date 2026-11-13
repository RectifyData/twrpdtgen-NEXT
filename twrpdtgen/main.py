#
# Copyright (C) 2026 The twrpdtgen-NEXT contributors
#
# SPDX-License-Identifier: Apache-2.0
#
"""Command-line interface for recovery device tree generation and extraction."""

from argparse import ArgumentParser
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from twrpdtgen import __version__ as version, current_path
from twrpdtgen.next_support import (
    NextOptions,
    parse_partition_size,
)


def _add_image_arguments(parser):
    parser.add_argument(
        "image",
        nargs="?",
        type=Path,
        help=(
            "primary recovery/boot image; omit for Easy Mode, or pass a "
            "folder/ZIP to auto-discover standard Android images"))
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
        return destination
    finally:
        manager.cleanup()


def build_parser():
    """Single authoritative generator CLI schema used by all frontends."""
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
            "vendor_boot",
            "init_boot"),
        default="auto",
        help=(
            "override detected recovery storage location"))
    parser.add_argument(
        "--recovery-fragment",
        help=(
            "vendor_boot fragment name or numeric index to use as the "
            "recovery source when automatic selection is ambiguous"))
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
        help="verified boot partition size in bytes or KiB/MiB/GiB")
    parser.add_argument(
        "--recovery-size",
        type=parse_partition_size,
        help="verified recovery partition size in bytes or KiB/MiB/GiB")
    parser.add_argument(
        "--super-size",
        type=parse_partition_size,
        help="verified super partition size in bytes or KiB/MiB/GiB")
    parser.add_argument(
        "--dynamic-group-size",
        type=parse_partition_size,
        help="verified dynamic group size in bytes or KiB/MiB/GiB")
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
    parser.add_argument("--cli", action="store_true",
                        help="force terminal mode (no GUI)")
    parser.add_argument("--gui", action="store_true",
                        help="open graphical mode with optional IMAGE")
    parser.add_argument("--web", action="store_true",
                        help="open the mobile-friendly localhost browser GUI")
    return parser


@dataclass(frozen=True)
class CLIExecutionResult:
    """Shared result for the CLI, desktop GUI and Android browser GUI."""
    tree: Optional[Path] = None
    archive: Optional[Path] = None
    extracted: Optional[Path] = None


def execute_cli_job(args, *, direct=False):
    """Run one CLI job. direct=True skips Easy Mode re-discovery for staged GUI inputs."""
    # The legacy unpacker dependencies are required only for actual CLI
    # generation, not to display --help or bring up a GUI.
    from sebaubuntu_libs.liblogging import setup_logging
    setup_logging(args.debug)
    from twrpdtgen.easy import SUPPORTED_IMAGE_NAMES
    easy_input = (
        args.image.is_dir()
        or args.image.suffix.lower() == ".zip"
        or args.image.name.lower() in SUPPORTED_IMAGE_NAMES
    )
    if (
            not direct
            and easy_input
            and not args.extract_only
            and not args.extract_to
            and args.boot_image is None
            and args.vendor_boot is None
            and args.init_boot is None
            and args.recovery_fragment is None
            and args.boot_size is None
            and args.recovery_size is None
            and args.super_size is None
            and args.dynamic_group_size is None
            and not args.git):
        from twrpdtgen.easy import generate_easy
        try:
            _, folder, bundle = generate_easy(
                args.image,
                tree_output=args.output,
                skeleton=args.skeleton,
                recovery_layout=args.recovery_layout,
                recovery_root_mode=args.recovery_root_mode,
                overwrite=args.overwrite,
            )
        except Exception as exc:
            raise ValueError(str(exc)) from exc
        print(f"\nGenerated candidate tree at {folder}")
        print(f"Portable ZIP: {bundle}")
        print(
            "Build and validate the generated tree for the target device "
            "before flashing."
        )
        return CLIExecutionResult(tree=folder, archive=bundle)

    if args.extract_only:
        extracted = _extract_only(args)
        return CLIExecutionResult(extracted=extracted)

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

    return CLIExecutionResult(tree=folder, extracted=extracted)



def main(*, cli_only=False):
    print(
        "TWRP device tree generator NEXT\n"
        f"Version {version}\n")

    parser = build_parser()
    args = parser.parse_args()

    if args.web:
        from twrpdtgen.webgui import main as web_main
        return web_main([])
    if args.gui:
        from twrpdtgen.gui import main as gui_main
        return gui_main(
            ["--source", str(args.image)] if args.image else [])
    if args.image is None:
        if cli_only or args.cli:
            parser.print_help()
            return 0
        from twrpdtgen.gui import can_launch_gui, main as gui_main
        if can_launch_gui():
            return gui_main([])
        # Termux has a full Android browser but typically not a Tk desktop.
        import os
        if (os.environ.get("TERMUX_VERSION")
                or "com.termux" in os.environ.get("PREFIX", "")):
            from twrpdtgen.webgui import main as web_main
            return web_main([])
        from twrpdtgen.easy import main as easy_main
        return easy_main([])

    return execute_cli_job(args)




def main_cli():
    """Run a CLI without ever opening Tk."""
    return main(cli_only=True)


if __name__ == "__main__":
    main()
