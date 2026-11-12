# Copyright (C) 2026 The twrpdtgen-NEXT contributors
# SPDX-License-Identifier: Apache-2.0
"""End-to-end cloud firmware -> TWRP device-tree generation."""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Iterable, Optional

from twrpdtgen.cloud_slice import (
    CloudSliceError,
    SliceResult,
    download_firmware,
    slice_firmware,
)
from twrpdtgen.next_support import NextOptions, parse_partition_size


@dataclass(frozen=True)
class CloudTreeResult:
    slice: SliceResult
    tree: Path
    archive: Path


def _archive_tree(tree: Path, archive: Path) -> Path:
    """Create a ZIP containing the generated device-tree directory."""
    tree = Path(tree)
    archive = Path(archive)
    if not tree.is_dir():
        raise FileNotFoundError(f"Generated tree does not exist: {tree}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.suffix.lower() != ".zip":
        archive = archive.with_suffix(".zip")
    if archive.exists():
        archive.unlink()

    # make_archive takes a base name without the .zip suffix.
    manufacturer = tree.parent.name
    created = shutil.make_archive(
        str(archive.with_suffix("")),
        "zip",
        root_dir=str(tree.parent.parent),
        base_dir=str(Path(manufacturer) / tree.name),
    )
    return Path(created)


def generate_tree_from_image(
        image: Path,
        tree_output: Path,
        *,
        skeleton: str = "auto",
        recovery_layout: str = "auto",
        recovery_root_mode: str = "auto",
        recovery_fragment: Optional[str] = None,
        boot_size: Optional[int] = None,
        recovery_size: Optional[int] = None,
        super_size: Optional[int] = None,
        dynamic_group_size: Optional[int] = None,
        overwrite: bool = False,
) -> Path:
    """Run the normal twrpdtgen DeviceTree pipeline for one recovery-bearing image."""
    from twrpdtgen.device_tree import DeviceTree

    options = NextOptions(
        skeleton=skeleton,
        recovery_layout=recovery_layout,
        recovery_root_mode=recovery_root_mode,
        boot_size=boot_size,
        recovery_size=recovery_size,
        super_size=super_size,
        dynamic_group_size=dynamic_group_size,
        overwrite=overwrite,
    )
    generator = DeviceTree(
        image=Path(image),
        options=options,
        recovery_fragment=recovery_fragment,
    )
    try:
        return generator.dump_to_folder(Path(tree_output), git=False)
    finally:
        generator.cleanup()


def fetch_and_generate_tree(
        model: str,
        region: str,
        *,
        partition: str = "recovery",
        package: str = "auto",
        member: Optional[str] = None,
        version: Optional[str] = None,
        threads: int = 8,
        samloader: Optional[Path] = None,
        work_dir: Optional[Path] = None,
        tree_output: Path = Path("output"),
        archive: Path = Path("twrp-device-tree.zip"),
        skeleton: str = "auto",
        recovery_layout: str = "auto",
        recovery_root_mode: str = "auto",
        recovery_fragment: Optional[str] = None,
        boot_size: Optional[int] = None,
        recovery_size: Optional[int] = None,
        super_size: Optional[int] = None,
        dynamic_group_size: Optional[int] = None,
        overwrite: bool = False,
        keep_firmware: bool = False,
        keep_image: bool = False,
        image_output: Optional[Path] = None,
) -> CloudTreeResult:
    """Download firmware in the cloud, slice one image, generate and ZIP a tree."""
    persistent = bool(work_dir or keep_firmware or keep_image)
    if persistent:
        cloud_work = Path(work_dir or Path.cwd() / ".twrpdtgen-cloud")
        cloud_work.mkdir(parents=True, exist_ok=True)
        temp_context = None
    else:
        temp_context = tempfile.TemporaryDirectory(
            prefix="twrpdtgen-cloud-tree-"
        )
        cloud_work = Path(temp_context.name)

    firmware = cloud_work / (
        f"{model.strip()}_{region.strip()}_firmware.zip"
    )
    requested_image = Path(image_output) if image_output else (
        cloud_work / (
            Path(partition).name
            if Path(partition).name.lower().endswith((".img", ".bin"))
            else f"{Path(partition).name}.img"
        )
    )
    if overwrite:
        requested_image.unlink(missing_ok=True)
        firmware.unlink(missing_ok=True)

    try:
        download_firmware(
            model,
            region,
            firmware,
            version=version,
            threads=threads,
            samloader=samloader,
        )
        sliced = slice_firmware(
            firmware,
            partition,
            output=requested_image,
            package=package,
            member=member,
            overwrite=overwrite,
        )
        tree = generate_tree_from_image(
            sliced.output,
            tree_output,
            skeleton=skeleton,
            recovery_layout=recovery_layout,
            recovery_root_mode=recovery_root_mode,
            recovery_fragment=recovery_fragment,
            boot_size=boot_size,
            recovery_size=recovery_size,
            super_size=super_size,
            dynamic_group_size=dynamic_group_size,
            overwrite=overwrite,
        )
        archive_path = _archive_tree(tree, archive)

        if not keep_firmware:
            firmware.unlink(missing_ok=True)
        if not keep_image and image_output is None:
            sliced.output.unlink(missing_ok=True)

        return CloudTreeResult(
            slice=sliced,
            tree=tree,
            archive=archive_path,
        )
    finally:
        if temp_context is not None:
            temp_context.cleanup()


def _colab_download(path: Path) -> None:
    try:
        from google.colab import files  # type: ignore
    except ImportError as exc:
        raise CloudSliceError(
            "--colab-download was requested outside Google Colab"
        ) from exc
    files.download(str(path))


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m twrpdtgen.cloud_tree",
        description=(
            "End-to-end Samsung cloud workflow: download/decrypt firmware, "
            "extract one recovery-bearing image, generate a TWRP device-tree "
            "candidate, ZIP it, and optionally download only that ZIP."
        ),
    )
    parser.add_argument("-m", "--model", required=True)
    parser.add_argument("-r", "--region", required=True)
    parser.add_argument("-v", "--version")
    parser.add_argument(
        "--partition",
        default="recovery",
        help="recovery-bearing Odin payload to extract (default: recovery)",
    )
    parser.add_argument(
        "--package",
        default="auto",
        help="AP/BL/CP/CSC/HOME_CSC/USERDATA or auto",
    )
    parser.add_argument("--member", help="exact TAR member override")
    parser.add_argument("-j", "--threads", type=int, default=8)
    parser.add_argument("--samloader", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument(
        "-o",
        "--tree-output",
        type=Path,
        default=Path("output"),
        help="parent directory for generated manufacturer/codename tree",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("twrp-device-tree.zip"),
        help="final ZIP path",
    )
    parser.add_argument(
        "--skeleton",
        choices=("auto", "omni", "twrp-12.1", "twrp-14.1"),
        default="auto",
    )
    parser.add_argument(
        "--recovery-layout",
        choices=("auto", "dedicated", "boot", "vendor_boot"),
        default="auto",
    )
    parser.add_argument(
        "--recovery-root-mode",
        choices=("auto", "minimal", "full"),
        default="auto",
    )
    parser.add_argument("--recovery-fragment")
    parser.add_argument("--boot-size", type=parse_partition_size)
    parser.add_argument("--recovery-size", type=parse_partition_size)
    parser.add_argument("--super-size", type=parse_partition_size)
    parser.add_argument("--dynamic-group-size", type=parse_partition_size)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--keep-firmware", action="store_true")
    parser.add_argument("--keep-image", action="store_true")
    parser.add_argument(
        "--image-output",
        type=Path,
        help="persistent extracted image path; implies keeping that image",
    )
    parser.add_argument(
        "--colab-download",
        action="store_true",
        help="download only the final generated tree ZIP in Google Colab",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(
            list(argv) if argv is not None else None
        )
        result = fetch_and_generate_tree(
            args.model,
            args.region,
            partition=args.partition,
            package=args.package,
            member=args.member,
            version=args.version,
            threads=args.threads,
            samloader=args.samloader,
            work_dir=args.work_dir,
            tree_output=args.tree_output,
            archive=args.archive,
            skeleton=args.skeleton,
            recovery_layout=args.recovery_layout,
            recovery_root_mode=args.recovery_root_mode,
            recovery_fragment=args.recovery_fragment,
            boot_size=args.boot_size,
            recovery_size=args.recovery_size,
            super_size=args.super_size,
            dynamic_group_size=args.dynamic_group_size,
            overwrite=args.overwrite,
            keep_firmware=args.keep_firmware,
            keep_image=(args.keep_image or args.image_output is not None),
            image_output=args.image_output,
        )
        print()
        print("Cloud TWRP device-tree generation complete")
        print(f"  firmware package: {result.slice.package_member}")
        print(f"  payload:          {result.slice.payload_member}")
        print(f"  tree:             {result.tree}")
        print(f"  archive:          {result.archive}")
        print(f"  image sha256:     {result.slice.sha256}")
        print()
        print(
            "The generated tree is a candidate source tree, not proof of "
            "recovery bootability. Verify target-specific kernel, fstab, "
            "AVB, encryption and partition details before building/flashing."
        )
        if args.colab_download:
            _colab_download(result.archive)
        return 0
    except (
            CloudSliceError,
            FileNotFoundError,
            FileExistsError,
            ValueError,
            OSError,
    ) as exc:
        print(f"[cloud-tree] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
