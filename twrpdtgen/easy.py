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
import tarfile
from typing import Iterable, Optional
import zipfile

from twrpdtgen.cloud_slice import _copy_payload

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


def _normalized_payload_name(name: str) -> str:
    lowered = PurePosixPath(name).name.lower()
    if lowered.endswith(".lz4"):
        lowered = lowered[:-4]
    return lowered


def _is_recovery_payload(name: str) -> bool:
    return _normalized_payload_name(name) in SUPPORTED_IMAGE_NAMES


def _extract_payload_stream(source, member_name: str, destination: Path) -> Path:
    name = PurePosixPath(member_name).name
    normalized = name[:-4] if name.lower().endswith(".lz4") else name
    output = destination / normalized
    if output.exists():
        raise EasyModeError(
            f"More than one archive member resolves to {output.name}. "
            "Use images from only one firmware build."
        )
    if name.lower().endswith(".lz4"):
        _copy_payload(source, name, output)
    else:
        with output.open("wb") as dst:
            shutil.copyfileobj(source, dst, 1024 * 1024)
    return output


def _choose_archive_members(names):
    safe = []
    for name in names:
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts:
            continue
        lowered = pure.name.lower()
        if lowered.endswith(".img") or lowered.endswith(".img.lz4"):
            safe.append(name)
    preferred = [name for name in safe if _is_recovery_payload(name)]
    if preferred:
        return preferred
    if len(safe) == 1:
        return safe
    if not safe:
        raise EasyModeError(
            "The archive contains no Android .img or .img.lz4 files."
        )
    raise EasyModeError(
        "The archive contains multiple images but none has a standard "
        "recovery/boot name. Extract the one recovery-bearing image first."
    )


def _safe_zip_images(
        archive: Path,
        destination: Path,
        *,
        depth: int = 0,
) -> int:
    """Extract useful Android image members, following one nested image ZIP."""
    try:
        bundle = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as exc:
        raise EasyModeError(f"That ZIP is damaged or invalid: {archive}") from exc

    with bundle:
        infos = {
            info.filename: info
            for info in bundle.infolist()
            if not info.is_dir()
        }
        try:
            selected = _choose_archive_members(infos)
        except EasyModeError:
            nested = [
                name for name in infos
                if PurePosixPath(name).name.lower().endswith(".zip")
            ]
            if len(nested) != 1 or depth >= 2:
                raise
            nested_path = destination / ".twrpdtgen-nested.zip"
            with bundle.open(infos[nested[0]]) as src, nested_path.open("wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            try:
                return _safe_zip_images(
                    nested_path,
                    destination,
                    depth=depth + 1,
                )
            finally:
                nested_path.unlink(missing_ok=True)

        for name in selected:
            with bundle.open(infos[name]) as src:
                _extract_payload_stream(src, name, destination)
    return len(selected)


def _safe_tar_images(archive: Path, destination: Path) -> int:
    """Extract only useful Android images from TAR/TAR.MD5/Odin packages."""
    try:
        bundle = tarfile.open(archive, mode="r:*")
    except tarfile.TarError as exc:
        raise EasyModeError(
            f"That TAR/TAR.MD5 package is damaged or unsupported: {archive}"
        ) from exc

    with bundle:
        members = {
            member.name: member
            for member in bundle.getmembers()
            if member.isfile()
        }
        try:
            selected = _choose_archive_members(members)
        except EasyModeError:
            nested = [
                name for name in members
                if PurePosixPath(name).name.lower().endswith(".zip")
            ]
            if len(nested) != 1:
                raise
            nested_path = destination / ".twrpdtgen-nested.zip"
            stream = bundle.extractfile(members[nested[0]])
            if stream is None:
                raise EasyModeError(
                    f"Could not read nested ZIP {nested[0]} from {archive.name}"
                )
            with stream, nested_path.open("wb") as dst:
                shutil.copyfileobj(stream, dst, 1024 * 1024)
            try:
                return _safe_zip_images(
                    nested_path,
                    destination,
                    depth=1,
                )
            finally:
                nested_path.unlink(missing_ok=True)

        for name in selected:
            stream = bundle.extractfile(members[name])
            if stream is None:
                raise EasyModeError(f"Could not read {name} from {archive.name}")
            with stream:
                _extract_payload_stream(stream, name, destination)
    return len(selected)


def _single_unambiguous_image(root: Path) -> Optional[Path]:
    images = [
        path for path in root.rglob("*")
        if path.is_file() and path.name.lower().endswith(".img")
    ]
    return images[0] if len(images) == 1 else None


def _copy_standard_companions(source: Path, destination: Path) -> None:
    """Copy likely same-slot companions without mixing A/B image sets."""
    available = {
        candidate.name.lower(): candidate
        for candidate in source.parent.iterdir()
        if candidate.is_file()
    }
    lowered = source.name.lower()
    slot = None
    if lowered.endswith("_a.img"):
        slot = "a"
    elif lowered.endswith("_b.img"):
        slot = "b"

    for role in ("recovery", "vendor_boot", "boot", "init_boot"):
        choices = []
        if slot is not None:
            choices.append(f"{role}_{slot}.img")
            choices.append(f"{role}.img")
        else:
            choices.extend((
                f"{role}.img",
                f"{role}_a.img",
                f"{role}_b.img",
            ))
        for name in choices:
            candidate = available.get(name)
            if candidate is None:
                continue
            output = destination / candidate.name
            if not output.exists():
                shutil.copy2(candidate, output)
            break


@contextmanager
def prepared_input(source: Path):
    """Yield (input directory, optional explicitly-selected primary image)."""
    source = Path(source).expanduser()
    if not source.exists():
        raise EasyModeError(f"Input does not exist: {source}")

    if source.is_dir():
        try:
            discover_images(source)
            yield source.resolve(), None
            return
        except ValueError:
            one = _single_unambiguous_image(source)
            if one is not None:
                yield source.resolve(), one.resolve()
                return
            raise

    if not source.is_file():
        raise EasyModeError(f"Input is not a normal file or folder: {source}")

    lowered = source.name.lower()
    supported = (
        lowered.endswith(".img")
        or lowered.endswith(".img.lz4")
        or lowered.endswith(".zip")
        or lowered.endswith(".tar")
        or lowered.endswith(".tar.md5")
        or lowered.endswith(".tgz")
        or lowered.endswith(".tar.gz")
        or lowered.endswith(".tar.xz")
        or lowered.endswith(".tar.bz2")
    )
    if not supported:
        raise EasyModeError(
            "Choose a folder, Android .img/.img.lz4, ZIP, TAR/TAR.MD5, or compressed TAR package."
        )

    with tempfile.TemporaryDirectory(prefix="twrpdtgen-easy-") as temp:
        root = Path(temp)

        if lowered.endswith(".zip"):
            _safe_zip_images(source, root)
            try:
                discover_images(root)
                yield root, None
            except ValueError:
                one = _single_unambiguous_image(root)
                if one is None:
                    raise
                yield root, one
            return

        if (
                lowered.endswith(".tar")
                or lowered.endswith(".tar.md5")
                or lowered.endswith(".tgz")
                or lowered.endswith(".tar.gz")
                or lowered.endswith(".tar.xz")
                or lowered.endswith(".tar.bz2")):
            _safe_tar_images(source, root)
            try:
                discover_images(root)
                yield root, None
            except ValueError:
                one = _single_unambiguous_image(root)
                if one is None:
                    raise
                yield root, one
            return

        if lowered.endswith(".img.lz4"):
            output_name = source.name[:-4]
            with source.open("rb") as src:
                selected = _extract_payload_stream(src, source.name, root)
            yield root, selected
            return

        # A deliberately selected single image stays the primary. For standard
        # names we also stage nearby standard companions automatically.
        selected = root / source.name
        shutil.copy2(source, selected)
        if source.name.lower() in SUPPORTED_IMAGE_NAMES:
            _copy_standard_companions(source, root)
        yield root, selected


def _explicit_role(path: Path) -> Optional[str]:
    name = path.name.lower()
    for role in ("recovery", "vendor_boot", "init_boot", "boot"):
        if name == f"{role}.img" or name in (
                f"{role}_a.img", f"{role}_b.img"):
            return role
    return None


def _generate_explicit_image(
        input_dir: Path,
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
    companions = None
    try:
        companions = discover_images(input_dir)
    except ValueError:
        companions = None

    selected_role = _explicit_role(image)
    generator = DeviceTree(
        image=image,
        options=options,
        boot_image=(
            companions.boot
            if companions is not None
            and selected_role != "boot"
            and companions.boot != image
            else None
        ),
        vendor_boot=(
            companions.vendor_boot
            if companions is not None
            and selected_role != "vendor_boot"
            and companions.vendor_boot != image
            else None
        ),
        init_boot=(
            companions.init_boot
            if companions is not None
            and selected_role != "init_boot"
            and companions.init_boot != image
            else None
        ),
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
                input_dir,
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
                ("Android image/archive", "*.img *.lz4 *.zip *.tar *.md5 *.tgz *.gz *.xz *.bz2"),
                ("Android image", "*.img *.lz4"),
                ("Firmware archive", "*.zip *.tar *.md5 *.tgz *.gz *.xz *.bz2"),
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
            "No input was provided. Pass a folder, .img/.img.lz4, ZIP, TAR, or TAR.MD5 path. "
            "Example: twrpdtgen ./firmware"
        )

    print()
    print("Easy mode")
    print("---------")
    print("Drag an Android image, firmware archive, or image folder")
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
        help="folder, Android image, ZIP, TAR/TAR.MD5, or compressed TAR; omit for picker/prompt",
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
