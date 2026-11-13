# Copyright (C) 2026 The twrpdtgen-NEXT contributors
# SPDX-License-Identifier: Apache-2.0
"""Portable source-tree ZIP export with Unix symlink preservation."""

from __future__ import annotations

from argparse import ArgumentParser
import os
from pathlib import Path
import stat
import time
from typing import Iterable, Optional
import zipfile


def _zip_symlink(
        bundle: zipfile.ZipFile,
        source: Path,
        arcname: str,
) -> None:
    """Store a POSIX symlink as a real ZIP symlink entry."""
    st = source.lstat()
    info = zipfile.ZipInfo(
        arcname,
        time.localtime(max(st.st_mtime, 315532800))[:6],
    )
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (
        (stat.S_IFLNK | stat.S_IMODE(st.st_mode)) << 16
    )
    info.external_attr |= 0x20
    target = os.readlink(source)
    bundle.writestr(
        info,
        target.encode("utf-8", errors="surrogateescape"),
    )


def archive_tree(
        tree: Path,
        archive: Path,
        *,
        include_stock_root: bool = False,
) -> Path:
    """ZIP one generated <manufacturer>/<codename> tree safely.

    The archive keeps the manufacturer/codename root, preserves POSIX symlinks,
    enables ZIP64, and excludes recovery/stock-root by default because that
    directory is an audit workspace rather than normal device-tree source.
    """
    tree = Path(tree)
    archive = Path(archive)
    if not tree.is_dir():
        raise FileNotFoundError(
            f"Generated tree does not exist: {tree}"
        )
    if not (tree / "AndroidProducts.mk").is_file():
        raise ValueError(
            "Expected a generated device-tree directory containing "
            "AndroidProducts.mk"
        )
    if tree.parent == tree or not tree.parent.name:
        raise ValueError(
            "Generated tree must be nested under a manufacturer directory"
        )

    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.suffix.lower() != ".zip":
        archive = archive.with_suffix(".zip")
    archive.unlink(missing_ok=True)

    manufacturer = tree.parent.name
    prefix = Path(manufacturer) / tree.name

    def skipped(relative: Path) -> bool:
        if include_stock_root:
            return False
        parts = relative.parts
        return (
            len(parts) >= 2
            and parts[0] == "recovery"
            and parts[1] == "stock-root"
        )

    with zipfile.ZipFile(
            archive,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
    ) as bundle:
        for root, dirs, files in os.walk(
                tree, topdown=True, followlinks=False):
            root_path = Path(root)
            relative_root = root_path.relative_to(tree)

            kept_dirs = []
            for name in sorted(dirs):
                path = root_path / name
                relative = relative_root / name
                if skipped(relative):
                    continue
                arcname = (prefix / relative).as_posix()
                if path.is_symlink():
                    _zip_symlink(bundle, path, arcname)
                    continue
                kept_dirs.append(name)
                info = zipfile.ZipInfo.from_file(
                    path,
                    arcname + "/",
                )
                bundle.writestr(info, b"")
            dirs[:] = kept_dirs

            for name in sorted(files):
                path = root_path / name
                relative = relative_root / name
                if skipped(relative):
                    continue
                arcname = (prefix / relative).as_posix()
                if path.is_symlink():
                    _zip_symlink(bundle, path, arcname)
                else:
                    bundle.write(path, arcname)

    return archive


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m twrpdtgen.tree_archive",
        description=(
            "ZIP a generated twrpdtgen-NEXT device tree while preserving "
            "Unix symlinks and excluding audit-only stock-root by default."
        ),
    )
    parser.add_argument(
        "tree",
        type=Path,
        help="generated <manufacturer>/<codename> tree directory",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("twrp-device-tree.zip"),
        help="output ZIP path",
    )
    parser.add_argument(
        "--include-stock-root",
        action="store_true",
        help="include recovery/stock-root in the ZIP",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(
        list(argv) if argv is not None else None
    )
    try:
        result = archive_tree(
            args.tree,
            args.output,
            include_stock_root=args.include_stock_root,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        parser.error(str(exc))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
