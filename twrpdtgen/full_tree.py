"""Enrich a generated TWRP recovery tree with available stock device files.

Generated source is never proof of bootability. No flash, partition mutation,
unsigned AVB bypass, or stock recovery executable replacement is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

RECOVERY_DEPENDENCIES = (
    "vendor/firmware", "vendor/etc/firmware", "vendor/etc/init",
    "vendor/etc/vintf", "vendor/etc/ueventd", "vendor/lib/modules",
    "vendor/lib64/modules", "odm/firmware", "odm/etc/firmware",
    "odm/etc/init", "odm/etc/vintf", "odm/lib/modules",
    "odm/lib64/modules", "vendor_dlkm/lib/modules",
    "odm_dlkm/lib/modules", "system_dlkm/lib/modules", "system_ext/etc/vintf",
    "system_ext/etc/init", "lib/modules", "lib64/modules",
)
BOARD_SIZES = {
    "boot": "BOARD_BOOTIMAGE_PARTITION_SIZE",
    "recovery": "BOARD_RECOVERYIMAGE_PARTITION_SIZE",
    "vendor_boot": "BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE",
    "init_boot": "BOARD_INIT_BOOT_IMAGE_PARTITION_SIZE",
    "dtbo": "BOARD_DTBOIMG_PARTITION_SIZE",
}


class CompletionError(ValueError):
    pass


def _safe(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise CompletionError("Unsafe firmware-relative path: " + str(relative))
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise CompletionError("Symlink in firmware path: " + str(cursor))
    return cursor


def _digest(file):
    hash = hashlib.sha256()
    with file.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hash.update(chunk)
    return hash.hexdigest()


def _dependencies(root, prefix=""):
    if root is None:
        return []
    root = Path(root).resolve()
    if not root.is_dir():
        raise CompletionError("Missing extracted firmware root: " + str(root))
    found = []
    for dirname in RECOVERY_DEPENDENCIES:
        if prefix and not dirname.startswith(prefix + "/"):
            continue
        relative = Path(dirname[len(prefix) + 1:] if prefix else dirname)
        folder = _safe(root, relative)
        if folder.is_symlink() or not folder.is_dir():
            continue
        for file in sorted(folder.rglob("*")):
            if file.is_symlink() or not file.is_file():
                continue
            original = file.relative_to(root)
            _safe(root, original)
            destination = Path(prefix) / original if prefix else original
            found.append((file, destination))
    return found


def complete_tree(tree, output, *, vendor_root=None, odm_root=None,
                  partition_roots=None, geometry=None):
    """Copy and enrich a generated tree without overwriting its source.

    geometry entries: {"recovery":{"bytes":67108864,"source":"GPT dump"}}.
    Incomplete available sources are recorded as blockers, never invented.
    """
    tree = Path(tree).resolve()
    output = Path(output).absolute()
    if not tree.is_dir():
        raise CompletionError("Source tree directory does not exist")
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(tree):
        raise CompletionError("Output exists or is inside source tree")
    for filename in ("AndroidProducts.mk", "BoardConfig.mk", "device.mk", "recovery.fstab"):
        if not _safe(tree, Path(filename)).is_file():
            raise CompletionError("Not a usable generated tree: missing " + filename)
    products = [p.name for p in tree.iterdir()
                if re.fullmatch(r"(?:omni|twrp)_[A-Za-z0-9_.-]+\.mk", p.name)]
    if len(products) != 1:
        raise CompletionError("Expected exactly one omni/twrp product makefile")
    geometry = geometry or {}
    if not isinstance(geometry, dict):
        raise CompletionError("Geometry must be a JSON object")
    audit = {"status": "unbuilt_unverified", "files": [],
             "partition_geometry": geometry, "blockers": []}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".twrpnext-", dir=output.parent) as work:
        stage = Path(work) / "tree"
        shutil.copytree(tree, stage, symlinks=True)
        overlay = _safe(stage, Path("recovery/root"))
        overlay.mkdir(parents=True, exist_ok=True)
        stock = _safe(tree, Path("recovery/stock-root"))
        collected = _dependencies(stock) if stock.is_dir() else []
        collected += _dependencies(vendor_root, "vendor")
        collected += _dependencies(odm_root, "odm")
        for role, root in (partition_roots or {}).items():
            if role not in ("vendor", "odm", "vendor_dlkm", "odm_dlkm", "system_dlkm", "system_ext"):
                raise CompletionError("Unsupported extracted partition role: " + str(role))
            if role == "vendor" and vendor_root is not None:
                continue
            if role == "odm" and odm_root is not None:
                continue
            collected += _dependencies(root, role)
        seen = {}
        for source, relative in collected:
            digest = _digest(source)
            if relative in seen:
                if seen[relative] != digest:
                    raise CompletionError('Conflicting stock and extracted firmware dependency: ' + relative.as_posix())
                continue
            seen[relative] = digest
            target = _safe(overlay, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if not target.is_file() or _digest(target) != digest:
                    raise CompletionError("Conflicting dependency: " + relative.as_posix())
            else:
                shutil.copy2(source, target)
            audit["files"].append({"path": relative.as_posix(), "sha256": digest})
        board_path = _safe(stage, Path("BoardConfig.mk"))
        board = board_path.read_text(encoding="utf-8")
        board = re.sub(r"(?m)^\s*ALLOW_MISSING_DEPENDENCIES\s*:?=\s*true\s*$",
                       "# Resolve missing dependencies explicitly.", board)
        for name, entry in geometry.items():
            if name not in BOARD_SIZES or not isinstance(entry, dict):
                raise CompletionError("Unknown partition geometry: " + str(name))
            size, provenance = entry.get("bytes"), entry.get("source")
            if type(size) is not int or size <= 0 or size % 512 != 0 or not isinstance(provenance, str) or not provenance.strip():
                raise CompletionError("Partition capacity requires positive sector-aligned bytes and source")
            key = BOARD_SIZES[name]
            pattern = r"(?m)^\s*" + re.escape(key) + r"\s*(?::=|\?=|=).*?$"
            if len(re.findall(pattern, board)) > 1:
                raise CompletionError("Conflicting partition size declarations: " + key)
            replacement = key + " := " + str(size)
            board = re.sub(pattern, lambda _: replacement, board) if re.search(pattern, board) else board + "\n" + replacement + "\n"
        board_path.write_text(board, encoding="utf-8")
        product = _safe(stage, Path(products[0]))
        text = product.read_text(encoding="utf-8")
        if "find-copy-subdir-files" not in text:
            matches = set(re.findall(r"device/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?=/device\.mk\))", text))
            if len(matches) != 1:
                raise CompletionError("Cannot determine device makefile source path")
            text += ("\nPRODUCT_COPY_FILES += $(call find-copy-subdir-files,*,"
                     + matches.pop() + "/recovery/root,recovery/root)\n")
            product.write_text(text, encoding="utf-8")
        if not geometry:
            audit["blockers"].append("No verified physical partition geometry")
        if not audit["files"]:
            audit["blockers"].append("No additional device runtime dependencies available")
        audit["blockers"].extend((
            "HAL/library closure, SELinux and encryption not validated",
            "Recovery output packaging and AVB/rollback not validated",
            "Source build, on-device boot and hardware functions not tested",
        ))
        _safe(stage, Path("fulltree-audit.json")).write_text(
            json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _safe(stage, Path("FULLTREE.md")).write_text(
            "# Completed recovery source tree\n\nNot verified bootable or flashable. See fulltree-audit.json.\n",
            encoding="utf-8")
        if output.exists() or output.is_symlink():
            raise CompletionError("Output appeared during completion")
        os.replace(stage, output)
    return audit


def complete_generated_tree(tree, *, vendor_root=None, odm_root=None,
                            partition_roots=None, geometry=None):
    """Transactionally enrich a generated tree without changing its path."""
    tree = Path(tree).resolve()
    target = tree.parent / ("." + tree.name + ".fulltree")
    backup = tree.parent / ("." + tree.name + ".backup")
    if target.exists() or backup.exists() or target.is_symlink() or backup.is_symlink():
        raise CompletionError("Temporary/backup path is already present")
    report = complete_tree(tree, target, vendor_root=vendor_root,
                           odm_root=odm_root, partition_roots=partition_roots,
                           geometry=geometry)
    os.replace(tree, backup)
    try:
        os.replace(target, tree)
    except Exception:
        os.replace(backup, tree)
        raise
    shutil.rmtree(backup)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="twrpdtgen-full-tree")
    parser.add_argument("tree", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--vendor-root", type=Path)
    parser.add_argument("--odm-root", type=Path)
    parser.add_argument("--geometry", type=Path, help="JSON file with capacity and provenance")
    args = parser.parse_args(argv)
    sizes = json.loads(args.geometry.read_text()) if args.geometry else {}
    report = complete_tree(args.tree, args.output, vendor_root=args.vendor_root,
                           odm_root=args.odm_root, geometry=sizes)
    print(json.dumps({"tree": str(args.output), "dependencies": len(report["files"]),
                      "blockers": report["blockers"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
