# Copyright (C) 2026 The twrpdtgen-NEXT contributors
# SPDX-License-Identifier: Apache-2.0
"""Beginner-friendly standalone workflow for twrpdtgen-NEXT."""

from __future__ import annotations

from argparse import ArgumentParser
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import os
import shutil
import sys
import tempfile
from typing import Iterable, Optional
import zipfile

from twrpdtgen.auto_tree import discover_images
from twrpdtgen.next_support import NextOptions
from twrpdtgen.tree_archive import archive_tree


SUPPORTED_IMAGE_NAMES = (
    "recovery.img",
    "recovery_a.img",
    "recovery_b.img",
    "vendor_boot.img",
    "vendor_boot_a.img",
    "vendor_boot_b.img",
    "boot.img",
    "boot_a.img",
    "boot_b.img",
    "init_boot.img",
    "init_boot_a.img",
    "init_boot_b.img",
)


class EasyModeError(RuntimeError):
    """Raised for errors that can be explained clearly to a non-expert."""


def _clean_drag_drop_path(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]
    return value.strip()


def _unique_path(path: Path) -> Path:
    """Return path or a numbered sibling without overwriting existing work."""
    path = Path(path)
    if not path.exists():
        return path
    stem = path.stem if path.suffix else path.name
    suffix = path.suffix
    parent = path.parent
    for number in range(2, 10000):
        candidate = parent / f"{stem}-{number}{suffix}"
        if not candidate.exists():
            return candidate
    raise EasyModeError(f"Too many existing outputs next to {path}")


def _default_destinations(source: Path) -> tuple[Path, Path]:
    source = Path(source)
    base = source.parent if source.is_file() else source
    if not os.access(base, os.W_OK):
        base = Path.cwd()
    tree_output = _unique_path(base / "twrpdtgen-output")
    archive = _unique_path(base / "twrp-device-tree.zip")
    return tree_output, archive


def _safe_zip_images(archive: Path, destination: Path) -> int:
    """Extract only Android .img members without allowing path traversal."""
    count = 0
    names = set()
    try:
        bundle = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as exc:
        raise EasyModeError(f"That ZIP is damaged or invalid: {archive}") from exc

    with bundle:
        for info in bundle.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".img"):
                continue
            pure = PurePosixPath(info.filename)
            if pure.is_absolute() or ".." in pure.parts:
                continue
            name = pure.name
            lowered = name.lower()
            if lowered in names:
                raise EasyModeError(
                    f"The ZIP contains more than one {name}. "
                    "Keep images from only one firmware/device in the input."
                )
            names.add(lowered)
            output = destination / name
            with bundle.open(info) as src, output.open("wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            count += 1

    if count == 0:
        raise EasyModeError(
            "The ZIP contains no .img files. Extract the firmware first, or "
            "provide recovery.img / boot.img / vendor_boot.img / init_boot.img."
        )
    return count


@contextmanager
def prepared_input(source: Path):
    """Yield a directory suitable for automatic image discovery.

    Directories are used as-is. ZIPs are safely unpacked into a temporary
    directory. Single images are staged with their original filename.
    """
    source = Path(source).expanduser()
    if not source.exists():
        raise EasyModeError(f"Input does not exist: {source}")

    if source.is_dir():
        yield source.resolve(), None
        return

    if not source.is_file():
        raise EasyModeError(f"Input is not a normal file or folder: {source}")

    suffix = source.suffix.lower()
    if suffix not in (".img", ".zip"):
        raise EasyModeError(
            "Choose a folder, an Android .img file, or a ZIP containing .img files."
        )

    with tempfile.TemporaryDirectory(prefix="twrpdtgen-easy-") as temp:
        root = Path(temp)
        if suffix == ".zip":
            _safe_zip_images(source, root)
            yield root, None
            return

        # If the selected image has a standard role name, copy nearby standard
        # companions from the same directory as a convenience.
        selected = root / source.name
        shutil.copy2(source, selected)
        if source.name.lower() in SUPPORTED_IMAGE_NAMES:
            for name in SUPPORTED_IMAGE_NAMES:
                candidate = source.parent / name
                destination = root / name
                if (
                        candidate.is_file()
                        and candidate.resolve() != source.resolve()
                        and not destination.exists()):
                    shutil.copy2(candidate, destination)
            yield root, None
            return

        # Arbitrarily-named single images cannot be role-discovered safely.
        # Preserve the path as an explicit primary instead of requiring rename.
        yield root, selected


def _generate_explicit_image(
        image: Path,
        tree_output: Path,
        archive: Path,
        *,
        skeleton: str,
        recovery_layout: str,
        recovery_root_mode: str,
        overwrite: bool,
):
    from twrpdtgen.device_tree import DeviceTree

    options = NextOptions(
        skeleton=skeleton,
        recovery_layout=recovery_layout,
        recovery_root_mode=recovery_root_mode,
        overwrite=overwrite,
    )
    generator = DeviceTree(
        image=image,
        options=options,
    )
    try:
        tree = generator.dump_to_folder(tree_output, git=False)
    finally:
        generator.cleanup()
    bundle = archive_tree(tree, archive)
    return None, tree, bundle


def generate_easy(
        source: Path,
        *,
        tree_output: Optional[Path] = None,
        archive: Optional[Path] = None,
        skeleton: str = "auto",
        recovery_layout: str = "auto",
        recovery_root_mode: str = "auto",
        overwrite: bool = False,
):
    """Generate using safe defaults from a folder, ZIP, or single image."""
    source = Path(source).expanduser()
    default_tree, default_archive = _default_destinations(source)
    tree_output = Path(tree_output) if tree_output else default_tree
    archive = Path(archive) if archive else default_archive

    if not overwrite:
        tree_output = _unique_path(tree_output)
        archive = _unique_path(archive)

    with prepared_input(source) as (input_dir, explicit_primary):
        if explicit_primary is not None:
            return _generate_explicit_image(
                explicit_primary,
                tree_output,
                archive,
                skeleton=skeleton,
                recovery_layout=recovery_layout,
                recovery_root_mode=recovery_root_mode,
                overwrite=overwrite,
            )

        images = discover_images(input_dir)
        from twrpdtgen.auto_tree import generate_from_directory

        images, tree, bundle = generate_from_directory(
            input_dir,
            tree_output,
            archive,
            skeleton=skeleton,
            recovery_layout=recovery_layout,
            recovery_root_mode=recovery_root_mode,
            overwrite=overwrite,
        )
        return images, tree, bundle


def _pick_with_tkinter() -> Optional[Path]:
    """Use a native picker when a graphical desktop is available."""
    if sys.platform != "win32" and not (
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="Choose Android recovery/boot image or ZIP",
            filetypes=[
                ("Android image or ZIP", "*.img *.zip"),
                ("Android image", "*.img"),
                ("ZIP archive", "*.zip"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            selected = filedialog.askdirectory(
                title="Or choose a folder containing Android images"
            )
        root.destroy()
        return Path(selected) if selected else None
    except Exception:
        try:
            root.destroy()
        except Exception:
            pass
        return None


def choose_input() -> Path:
    selected = _pick_with_tkinter()
    if selected is not None:
        return selected

    if not sys.stdin.isatty():
        raise EasyModeError(
            "No input was provided. Pass a folder, .img, or ZIP path. "
            "Example: twrpdtgen ./firmware"
        )

    print()
    print("Easy mode")
    print("---------")
    print("Drag a recovery/boot .img, firmware-image ZIP, or image folder")
    print("into this window, then press Enter.")
    while True:
        value = _clean_drag_drop_path(input("> "))
        if not value:
            print("Nothing selected. Drag a file/folder here, or press Ctrl+C to exit.")
            continue
        path = Path(value).expanduser()
        if path.exists():
            return path
        print(f"Not found: {path}")


def _friendly_failure(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    hints = []
    if "ambiguous" in lowered:
        hints.append(
            "Keep images from one firmware build only, or remove the duplicate slot/build."
        )
    if "no supported android image" in lowered:
        hints.append(
            "Expected recovery.img, vendor_boot.img, boot.img, or init_boot.img."
        )
    if "already exists" in lowered:
        hints.append(
            "Easy mode normally creates a new numbered output. Use --overwrite only if replacement is intentional."
        )
    if "ramdisk" in lowered and "recovery" in lowered:
        hints.append(
            "This image may not contain the recovery ramdisk; provide the matching vendor_boot/boot/init_boot companions."
        )
    if hints:
        return message + "\n" + "\n".join(f"Hint: {hint}" for hint in hints)
    return message


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="twrpdtgen-easy",
        description=(
            "Beginner-friendly twrpdtgen-NEXT: choose a folder, .img, or ZIP "
            "and let NEXT detect the normal recovery/boot layout automatically."
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="folder, Android .img, or ZIP; omit to open easy picker/prompt",
    )
    parser.add_argument("-o", "--tree-output", type=Path)
    parser.add_argument("--archive", type=Path)
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
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(
        list(argv) if argv is not None else None
    )
    try:
        source = args.input or choose_input()
        print()
        print(f"Input: {source}")
        print("Detecting the device image layout automatically...")
        images, tree, bundle = generate_easy(
            source,
            tree_output=args.tree_output,
            archive=args.archive,
            skeleton=args.skeleton,
            recovery_layout=args.recovery_layout,
            recovery_root_mode=args.recovery_root_mode,
            overwrite=args.overwrite,
        )

        if images is not None:
            print("\nDetected:")
            for role, path in images.as_dict().items():
                if role == "primary":
                    continue
                if path is not None:
                    marker = " [primary]" if path == images.primary else ""
                    print(f"  {role:11}: {path.name}{marker}")

        print("\nDone.")
        print(f"Device tree: {tree}")
        print(f"ZIP:         {bundle}")
        print()
        print(
            "The generated tree is a bring-up candidate. Build and validate it "
            "for the target device before flashing."
        )
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:
        print(
            "\nCould not generate the tree:\n"
            + _friendly_failure(exc),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
