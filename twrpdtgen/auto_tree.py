# Copyright (C) 2026 The twrpdtgen-NEXT contributors
# SPDX-License-Identifier: Apache-2.0
"""Automatic discovery and generation from a folder of Android boot images."""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict, Iterable, Optional

from twrpdtgen.next_support import NextOptions, parse_partition_size
from twrpdtgen.tree_archive import archive_tree


_ROLE_PATTERN = re.compile(
    r"^(recovery|vendor_boot|init_boot|boot)(?:_([ab]))?\.img$",
    flags=re.IGNORECASE,
)
_ROLE_ORDER = ("recovery", "vendor_boot", "boot", "init_boot")


@dataclass(frozen=True)
class DiscoveredImages:
    primary: Path
    recovery: Optional[Path]
    boot: Optional[Path]
    vendor_boot: Optional[Path]
    init_boot: Optional[Path]

    def as_dict(self) -> Dict[str, Optional[Path]]:
        return {
            "primary": self.primary,
            "recovery": self.recovery,
            "boot": self.boot,
            "vendor_boot": self.vendor_boot,
            "init_boot": self.init_boot,
        }


def _candidate_rank(root: Path, path: Path, slot: Optional[str]):
    relative = path.relative_to(root)
    slot_rank = {None: 0, "a": 1, "b": 2}[slot]
    return (slot_rank, len(relative.parts), relative.as_posix().lower())


def discover_images(root: Path) -> DiscoveredImages:
    """Find conventional Android recovery/boot images without user typing.

    Exact unsuffixed names win, then slot A, then slot B. Shallower paths win
    within the same slot class. Ambiguous equally-ranked files are rejected
    instead of silently picking a random firmware variant.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Image input directory does not exist: {root}")

    candidates = {role: [] for role in _ROLE_ORDER}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        match = _ROLE_PATTERN.fullmatch(path.name)
        if match is None:
            continue
        role = match.group(1).lower()
        slot = match.group(2).lower() if match.group(2) else None
        candidates[role].append((path, slot))

    selected = {}
    for role, entries in candidates.items():
        if not entries:
            selected[role] = None
            continue
        ranked = sorted(
            entries,
            key=lambda item: _candidate_rank(root, item[0], item[1]),
        )
        best_rank = _candidate_rank(root, ranked[0][0], ranked[0][1])
        ties = [
            item[0]
            for item in ranked
            if _candidate_rank(root, item[0], item[1])[:2]
            == best_rank[:2]
        ]
        if len(ties) > 1:
            names = ", ".join(
                item.relative_to(root).as_posix()
                for item in ties
            )
            raise ValueError(
                f"Ambiguous {role}.img candidates: {names}"
            )
        selected[role] = ranked[0][0]

    primary = (
        selected["recovery"]
        or selected["vendor_boot"]
        or selected["boot"]
        or selected["init_boot"]
    )
    if primary is None:
        raise ValueError(
            "No supported Android image found. Upload recovery.img, boot.img, "
            "vendor_boot.img or init_boot.img (slot _a/_b names are also accepted)."
        )

    return DiscoveredImages(
        primary=primary,
        recovery=selected["recovery"],
        boot=selected["boot"],
        vendor_boot=selected["vendor_boot"],
        init_boot=selected["init_boot"],
    )


def generate_from_directory(
        input_dir: Path,
        tree_output: Path,
        archive: Path,
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
        include_stock_root: bool = False,
):
    """Auto-discover images, run DeviceTree, then create the portable ZIP."""
    from twrpdtgen.device_tree import DeviceTree

    images = discover_images(input_dir)
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

    primary = images.primary
    generator = DeviceTree(
        image=primary,
        options=options,
        boot_image=(
            images.boot
            if images.boot is not None and images.boot != primary
            else None
        ),
        vendor_boot=(
            images.vendor_boot
            if images.vendor_boot is not None
            and images.vendor_boot != primary
            else None
        ),
        init_boot=(
            images.init_boot
            if images.init_boot is not None
            and images.init_boot != primary
            else None
        ),
        recovery_fragment=recovery_fragment,
    )
    try:
        tree = generator.dump_to_folder(
            Path(tree_output),
            git=False,
        )
    finally:
        generator.cleanup()

    bundle = archive_tree(
        tree,
        Path(archive),
        include_stock_root=include_stock_root,
    )
    return images, tree, bundle


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m twrpdtgen.auto_tree",
        description=(
            "Automatically discover conventional recovery/boot image filenames "
            "in a directory, generate a candidate TWRP tree, and ZIP it."
        ),
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="folder containing uploaded/extracted Android .img files",
    )
    parser.add_argument(
        "-o",
        "--tree-output",
        type=Path,
        default=Path("output"),
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("twrp-device-tree.zip"),
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
    parser.add_argument("--include-stock-root", action="store_true")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(
        list(argv) if argv is not None else None
    )
    try:
        images, tree, bundle = generate_from_directory(
            args.input_dir,
            args.tree_output,
            args.archive,
            skeleton=args.skeleton,
            recovery_layout=args.recovery_layout,
            recovery_root_mode=args.recovery_root_mode,
            recovery_fragment=args.recovery_fragment,
            boot_size=args.boot_size,
            recovery_size=args.recovery_size,
            super_size=args.super_size,
            dynamic_group_size=args.dynamic_group_size,
            overwrite=args.overwrite,
            include_stock_root=args.include_stock_root,
        )
    except (
            FileNotFoundError,
            FileExistsError,
            ValueError,
            OSError,
    ) as exc:
        parser.error(str(exc))

    print("Auto-detected images:")
    for role, path in images.as_dict().items():
        if role == "primary":
            continue
        if path is not None:
            marker = " [primary]" if path == images.primary else ""
            print(f"  {role:11}: {path}{marker}")
    print(f"Generated tree: {tree}")
    print(f"Archive: {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
