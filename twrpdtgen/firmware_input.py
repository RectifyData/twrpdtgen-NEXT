# Copyright (C) 2026 The twrpdtgen-NEXT contributors
# SPDX-License-Identifier: Apache-2.0
"""Read-only import of Samsung Odin, Motorola fastboot and Google factory firmware.

The staging tree is disposable. No source image is edited, no device commands run,
and extracted contents are never promised to produce a bootable recovery.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
from typing import Dict, List, Optional

from twrpdtgen.tool_bootstrap import (
    find_lpunpack, find_extractor, translated_path, ToolInstallError,
)
import zipfile

BOOT_ROLES = ("recovery", "boot", "vendor_boot", "init_boot")
FILESYSTEM_ROLES = ("vendor", "odm", "vendor_dlkm", "odm_dlkm", "system_dlkm", "system_ext")
EXTRA_ROLES = ("super", "dtbo", "vbmeta", "vbmeta_system", "vbmeta_vendor", "system", "product")
ROLES = frozenset(BOOT_ROLES + FILESYSTEM_ROLES + EXTRA_ROLES)
# Odin calls certain ext4 files *.img.ext4[.lz4]. Keep the canonical *.img name.
IMAGE_NAME = re.compile(r"^(?P<role>[a-z][a-z0-9_]*?)(?:_(?P<slot>a|b))?\.img(?:\.ext4)?(?P<lz4>\.lz4)?$", re.I)
CHUNK_NAME = re.compile(r"^(?P<role>[a-z][a-z0-9_]*?)(?:_(?P<slot>a|b))?\.img_sparsechunk\.(?P<index>\d+)$", re.I)
SPARSE_MAGIC = 0xED26FF3A
MAX_IMAGE_BYTES = 64 * 1024**3
MAX_TOTAL_BYTES = 128 * 1024**3
CHUNK_BYTES = 4 * 1024**2


class FirmwareInputError(RuntimeError):
    """Unsupported, corrupt or contradictory firmware; the source is untouched."""


@dataclass
class PreparedFirmware:
    images: Path
    roots: Dict[str, Path] = field(default_factory=dict)
    sources: List[dict] = field(default_factory=list)
    tools: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)

    def audit(self) -> dict:
        return dict(source_images=self.sources, partition_roots=sorted(self.roots),
                    external_tools=self.tools, warnings=self.warnings,
                    blockers=self.blockers)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(CHUNK_BYTES), b''):
            h.update(data)
    return h.hexdigest()


def _relative_member(name: str) -> Optional[PurePosixPath]:
    if '\x00' in name:
        return None
    # Backslashes are separators on Windows even when parsing on Linux.
    name = name.replace('\\', '/')
    value = PurePosixPath(name)
    if value.is_absolute() or any(part in ('..', '.') for part in value.parts):
        return None
    return value


def _canonical_image(filename: str) -> Optional[str]:
    rel = _relative_member(filename)
    if rel is None:
        return None
    found = IMAGE_NAME.fullmatch(rel.name)
    if found is None or found.group('role').lower() not in ROLES:
        return None
    suffix = '_' + found.group('slot').lower() if found.group('slot') else ''
    return found.group('role').lower() + suffix + '.img'


def _sparsechunk_name(filename: str):
    rel = _relative_member(filename)
    if rel is None:
        return None
    match = CHUNK_NAME.fullmatch(rel.name)
    if not match or match.group('role').lower() not in ROLES:
        return None
    suffix = '_' + match.group('slot').lower() if match.group('slot') else ''
    return match.group('role').lower() + suffix + '.img', int(match.group('index'))


def _archive_type(path: Path) -> Optional[str]:
    lower = path.name.lower()
    if lower.endswith('.zip'):
        return 'zip'
    if lower.endswith(('.tar', '.tar.md5', '.tgz', '.tar.gz', '.tar.xz', '.tar.bz2')):
        return 'tar'
    return None


def _copy_limited(stream, target: Path, limit: int) -> int:
    n = 0
    with target.open('wb') as output:
        while True:
            data = stream.read(CHUNK_BYTES)
            if not data:
                break
            n += len(data)
            if n > limit:
                raise FirmwareInputError('Uncompressed image exceeds extraction limit')
            output.write(data)
    return n


def _write_image(stream, filename: str, destination: Path, entries: dict, total: list,
                 chunks: dict, size_hint: Optional[int] = None):
    target_name = _canonical_image(filename)
    chunk_key = _sparsechunk_name(filename)
    if target_name is None and chunk_key is None:
        return
    if size_hint is not None and size_hint > MAX_IMAGE_BYTES:
        raise FirmwareInputError('Oversized firmware image: ' + filename)
    if chunk_key:
        target_name, index = chunk_key
        group = chunks.setdefault(target_name, {})
        if index in group:
            raise FirmwareInputError('Duplicate sparsechunk: ' + filename)
        output_name = '.' + target_name + '.sparsechunk.' + str(index)
    else:
        index = None
        output_name = target_name
        if target_name in entries:
            raise FirmwareInputError('Duplicate partition image ' + target_name + '; do not mix firmware builds')
    print(f'[firmware] Staging {filename}...', flush=True)
    tmp = destination / ('.' + output_name + '.partial')
    target = destination / output_name
    if target.exists():
        raise FirmwareInputError('Duplicate firmware member: ' + filename)
    try:
        if filename.lower().endswith('.lz4'):
            try:
                import lz4.frame
            except ImportError as exc:
                raise FirmwareInputError('Samsung .lz4 requires: python -m pip install lz4') from exc
            with lz4.frame.open(stream, 'rb') as expanded:
                n = _copy_limited(expanded, tmp, min(MAX_IMAGE_BYTES, MAX_TOTAL_BYTES - total[0]))
        else:
            n = _copy_limited(stream, tmp, min(MAX_IMAGE_BYTES, MAX_TOTAL_BYTES - total[0]))
        if n <= 0:
            raise FirmwareInputError('Empty firmware image: ' + filename)
        os.replace(tmp, target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    total[0] += n
    if chunk_key:
        group[index] = target
    else:
        entries[target_name] = dict(name=filename, bytes=n, sha256=_sha256(target))


def _archive_member(stream, member_name: str, size: int, images: Path,
                    entries: dict, total: list, chunks: dict, depth: int):
    rel = _relative_member(member_name)
    if rel is None:
        return
    if _canonical_image(member_name) is not None or _sparsechunk_name(member_name) is not None:
        _write_image(stream, member_name, images, entries, total, chunks, size_hint=size)
    elif _archive_type(Path(rel.name)):
        if depth >= 4:
            raise FirmwareInputError('Nested firmware archive exceeds 4 levels')
        if size > MAX_IMAGE_BYTES:
            raise FirmwareInputError('Oversized nested firmware archive: ' + member_name)
        # The suffix retains '.zip' or '.tar.md5' for detection.
        with tempfile.NamedTemporaryFile(prefix='.nested-', suffix='-' + rel.name,
                                         dir=images, delete=False) as tmp:
            path = Path(tmp.name)
            copied = 0
            try:
                while True:
                    data = stream.read(CHUNK_BYTES)
                    if not data:
                        break
                    copied += len(data)
                    if copied > MAX_IMAGE_BYTES:
                        raise FirmwareInputError('Nested archive exceeded staging limit')
                    tmp.write(data)
            except Exception:
                path.unlink(missing_ok=True)
                raise
        try:
            _stage_archive(path, images, entries, total, chunks, depth + 1)
        finally:
            path.unlink(missing_ok=True)


def _verify_odin_md5(archive: Path):
    """Validate a present Odin trailing 32-character MD5 before extracting."""
    if not archive.name.lower().endswith('.tar.md5') or archive.stat().st_size < 32:
        return
    with archive.open('rb') as stream:
        stream.seek(-32, os.SEEK_END)
        trailer = stream.read(32)
        if re.fullmatch(rb'[a-fA-F0-9]{32}', trailer) is None:
            return  # Some distributors rename an ordinary TAR to .tar.md5.
        stream.seek(0)
        digest = hashlib.md5()  # checksum supplied by Samsung archive format
        remaining = archive.stat().st_size - 32
        while remaining:
            chunk = stream.read(min(remaining, CHUNK_BYTES))
            if not chunk:
                raise FirmwareInputError('Truncated Samsung TAR.MD5 archive')
            digest.update(chunk)
            remaining -= len(chunk)
        if digest.hexdigest().encode('ascii') != trailer.lower():
            raise FirmwareInputError('Samsung TAR.MD5 checksum mismatch: ' + archive.name)


def _stage_archive(archive: Path, images: Path, entries: dict, total: list,
                   chunks: dict, depth: int = 0):
    kind = _archive_type(archive)
    if kind is None:
        raise FirmwareInputError('Unsupported firmware archive: ' + archive.name)
    if kind == 'tar':
        _verify_odin_md5(archive)
    try:
        if kind == 'zip':
            with zipfile.ZipFile(archive) as z:
                for member in z.infolist():
                    if member.is_dir() or ((member.external_attr >> 16) & 0o170000) == 0o120000:
                        continue
                    with z.open(member) as stream:
                        _archive_member(stream, member.filename, member.file_size, images,
                                        entries, total, chunks, depth)
        else:
            # Python tarfile tolerates the Odin .tar.md5 checksum trailer.
            with tarfile.open(archive, 'r:*') as tar:
                for member in tar:
                    if not member.isfile():
                        continue
                    stream = tar.extractfile(member)
                    if stream is None:
                        raise FirmwareInputError('Unreadable TAR member: ' + member.name)
                    with stream:
                        _archive_member(stream, member.name, member.size, images,
                                        entries, total, chunks, depth)
    except (tarfile.TarError, zipfile.BadZipFile, EOFError) as exc:
        raise FirmwareInputError('Invalid firmware archive ' + archive.name + ': ' + str(exc)) from exc


def _stage_directory(root: Path, images: Path, entries: dict, total: list, chunks: dict):
    files = []
    for candidate in sorted(root.rglob('*')):
        if candidate.is_symlink() or not candidate.is_file() or images in candidate.parents:
            continue
        files.append(candidate)
    for candidate in files:
        if _canonical_image(candidate.name) or _sparsechunk_name(candidate.name):
            with candidate.open('rb') as stream:
                _write_image(stream, candidate.name, images, entries, total, chunks,
                             size_hint=candidate.stat().st_size)
    for candidate in files:
        if _archive_type(candidate):
            _stage_archive(candidate, images, entries, total, chunks)


def _write_sparse_chunk(source: Path, output, claimed: list, expected_blks: int,
                        expected_block_size: int):
    with source.open('rb') as stream:
        header = stream.read(28)
        if len(header) != 28:
            raise FirmwareInputError('Truncated Motorola sparsechunk header')
        magic, major, minor, file_h, chunk_h, block_size, blocks, count, checksum = struct.unpack('<IHHHHIIII', header)
        if magic != SPARSE_MAGIC or major != 1 or file_h < 28 or chunk_h < 12:
            raise FirmwareInputError('Motorola sparsechunk is not Android sparse v1: ' + source.name)
        if block_size != expected_block_size or blocks != expected_blks:
            raise FirmwareInputError('Motorola sparsechunks disagree on partition geometry')
        if file_h > 28:
            stream.seek(file_h - 28, os.SEEK_CUR)
        offset = 0
        for _ in range(count):
            hdr = stream.read(chunk_h)
            if len(hdr) != chunk_h:
                raise FirmwareInputError('Truncated sparsechunk chunk descriptor')
            kind, _, span, total = struct.unpack('<HHII', hdr[:12])
            length = span * block_size
            if offset + length > expected_blks * block_size:
                raise FirmwareInputError('Sparsechunk writes outside super partition')
            if kind == 0xCAC3:
                if total != chunk_h:
                    raise FirmwareInputError('Invalid DONT_CARE chunk length')
            elif kind == 0xCAC4:
                if span != 0 or total != chunk_h + 4 or len(stream.read(4)) != 4:
                    raise FirmwareInputError('Invalid sparsechunk CRC chunk')
                continue
            else:
                if kind not in (0xCAC1, 0xCAC2):
                    raise FirmwareInputError('Unknown sparsechunk encoding')
                if total != chunk_h + (length if kind == 0xCAC1 else 4):
                    raise FirmwareInputError('Malformed sparsechunk payload length')
                if length:
                    start, end = offset, offset + length
                    for lo, hi in claimed:
                        if lo < end and start < hi:
                            raise FirmwareInputError('Motorola sparsechunks overlap written blocks')
                    claimed.append((start, end))
                output.seek(offset)
                if kind == 0xCAC1:
                    remain = length
                    while remain:
                        data = stream.read(min(remain, CHUNK_BYTES))
                        if not data:
                            raise FirmwareInputError('Truncated Motorola sparsechunk payload')
                        output.write(data)
                        remain -= len(data)
                else:
                    word = stream.read(4)
                    if len(word) != 4:
                        raise FirmwareInputError('Truncated Motorola sparse fill')
                    fill = word * (CHUNK_BYTES // 4)
                    remain = length
                    while remain:
                        part = fill[:min(remain, len(fill))]
                        output.write(part)
                        remain -= len(part)
            offset += length
        if offset != expected_blks * block_size:
            raise FirmwareInputError('Sparsechunk does not declare a complete logical extent')


def _join_sparsechunks(images: Path, entries: dict, chunks: dict, total: list):
    for name, indexed in sorted(chunks.items()):
        if name in entries:
            raise FirmwareInputError('Conflicting whole image and Motorola sparsechunks for ' + name)
        numbers = sorted(indexed)
        if numbers != list(range(len(numbers))):
            raise FirmwareInputError('Missing Motorola sparsechunk sequence for ' + name + '; expected 0..N')
        geometry = None
        for source in indexed.values():
            with source.open('rb') as f:
                header = f.read(28)
            if len(header) != 28:
                raise FirmwareInputError('Truncated Motorola sparsechunk')
            magic, major, _, f_header, c_header, block_size, blocks, _, _ = struct.unpack('<IHHHHIIII', header)
            if magic != SPARSE_MAGIC or major != 1 or f_header < 28 or c_header < 12:
                raise FirmwareInputError('Motorola chunk is not Android sparse format: ' + source.name)
            if geometry is None:
                geometry = (blocks, block_size)
            elif geometry != (blocks, block_size):
                raise FirmwareInputError('Motorola sparsechunk geometry mismatch: ' + name)
        blocks, block_size = geometry
        size = blocks * block_size
        if size > MAX_IMAGE_BYTES or total[0] + size > MAX_TOTAL_BYTES:
            raise FirmwareInputError('Merged Motorola image exceeds staging limit')
        output = images / name
        claimed = []
        with output.open('w+b') as combined:
            combined.truncate(size)
            for number in numbers:
                _write_sparse_chunk(indexed[number], combined, claimed, blocks, block_size)
        total[0] += size
        entries[name] = dict(name='Motorola sparsechunks 0..' + str(numbers[-1]),
                             bytes=size, sha256=_sha256(output))
        for source in indexed.values():
            source.unlink()


def _sparse_to_raw(image: Path, raw: Path):
    with image.open('rb') as f:
        header = f.read(28)
        if len(header) != 28:
            raise FirmwareInputError('Truncated sparse header')
        magic, major, _, f_header, c_header, block_size, blocks, count, _ = struct.unpack('<IHHHHIIII', header)
        if magic != SPARSE_MAGIC or major != 1 or f_header < 28 or c_header < 12:
            raise FirmwareInputError('Invalid Android sparse header')
        if block_size * blocks > MAX_IMAGE_BYTES:
            raise FirmwareInputError('Sparse image expands beyond 64 GiB')
        if f_header > 28:
            f.seek(f_header - 28, os.SEEK_CUR)
        written = 0
        with raw.open('w+b') as out:
            for _ in range(count):
                chunk = f.read(c_header)
                if len(chunk) != c_header:
                    raise FirmwareInputError('Truncated sparse chunk header')
                kind, _, span, size = struct.unpack('<HHII', chunk[:12])
                length = span * block_size
                if written + length > block_size * blocks:
                    raise FirmwareInputError('Sparse data exceeds declared image size')
                if kind == 0xCAC1 and size == c_header + length:
                    remain = length
                    while remain:
                        part = f.read(min(remain, CHUNK_BYTES))
                        if not part:
                            raise FirmwareInputError('Truncated sparse raw data')
                        out.write(part)
                        remain -= len(part)
                elif kind == 0xCAC2 and size == c_header + 4:
                    fill = f.read(4)
                    if len(fill) != 4:
                        raise FirmwareInputError('Truncated sparse fill')
                    unit = fill * (CHUNK_BYTES // 4)
                    remain = length
                    while remain:
                        part = unit[:min(remain, len(unit))]
                        out.write(part)
                        remain -= len(part)
                elif kind == 0xCAC3 and size == c_header:
                    out.seek(length, os.SEEK_CUR)
                elif kind == 0xCAC4 and span == 0 and size == c_header + 4 and len(f.read(4)) == 4:
                    continue
                else:
                    raise FirmwareInputError('Invalid Android sparse chunk')
                written += length
            if written != blocks * block_size:
                raise FirmwareInputError('Sparse image has incomplete logical coverage')
            out.truncate(written)


def _raw_image(image: Path, scratch: Path) -> Path:
    with image.open('rb') as stream:
        magic = stream.read(4)
    if magic != struct.pack('<I', SPARSE_MAGIC):
        return image
    raw = scratch / (image.stem + '-raw.img')
    _sparse_to_raw(image, raw)
    return raw


def _filesystem_kind(path: Path) -> str:
    with path.open('rb') as image:
        image.seek(1024)
        superblock = image.read(64)
    if len(superblock) >= 58 and superblock[56:58] == b'\x53\xef':
        return 'ext4'
    if superblock[:4] == b'\xe2\xe1\xf5\xe0':
        return 'erofs'
    return 'unknown'


def _run_external(args, label):
    print(f'[firmware] {label}...', flush=True)
    try:
        result = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors='replace',
                                timeout=3600, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FirmwareInputError(label + ': ' + str(exc)) from exc
    if os.environ.get('TDTNEXT_FOREGROUND') == '1' and result.stdout:
        print(result.stdout, end='' if result.stdout.endswith('\n') else '\n', flush=True)
    if result.returncode != 0:
        raise FirmwareInputError(label + ': ' + result.stdout[-2500:])
    return result.stdout


def _unpack_super(source: Path, scratch: Path, prepared: PreparedFirmware,
                  entries: dict, *, auto_install: bool = True):
    try:
        command, description = find_lpunpack(auto_install=auto_install)
    except ToolInstallError as exc:
        raise FirmwareInputError(str(exc)) from exc
    prepared.tools['lpunpack'] = description
    raw = _raw_image(source, scratch)
    output = scratch / 'logical'
    output.mkdir(parents=True, exist_ok=True)
    # Python liblp uses '-o DIR'; the native Android binary uses positional DIR.
    args = ([*command, raw, '-o', output] if description.startswith('Python liblp ')
            else [*command, raw, output])
    _run_external(args, 'lpunpack')
    for item in sorted(output.iterdir()):
        name = _canonical_image(item.name)
        if name is None or item.is_symlink() or not item.is_file() or name in entries:
            continue
        target = prepared.images / name
        shutil.copyfile(item, target)
        entries[name] = dict(name='super.img/' + item.name, bytes=target.stat().st_size,
                             sha256=_sha256(target))
        prepared.sources.append(dict(image=name, **entries[name]))


def _extract_partition(image: Path, role: str, scratch: Path, prepared: PreparedFirmware,
                       *, auto_install: bool = True):
    raw = _raw_image(image, scratch)
    kind = _filesystem_kind(raw)
    if kind == 'unknown':
        raise FirmwareInputError(role + ': not an ext4/EROFS filesystem image')
    output = scratch / 'partition-roots' / role
    output.mkdir(parents=True)
    executable = 'debugfs' if kind == 'ext4' else 'fsck.erofs'
    try:
        prefix, description, via_wsl = find_extractor(executable, auto_install=auto_install)
        source_path = translated_path(raw, via_wsl=via_wsl)
        dest_path = translated_path(output, via_wsl=via_wsl)
    except ToolInstallError as exc:
        raise FirmwareInputError(role + ': ' + str(exc)) from exc
    prepared.tools[executable] = description
    if kind == 'ext4':
        # quote paths inside debugfs' own command parser (not a shell).
        escaped = dest_path.replace('\\', '\\\\').replace('"', '\\"')
        report = _run_external([*prefix, '-R', 'rdump / "' + escaped + '"', source_path],
                               role + ' ext4 extraction')
        if 'Filesystem not open' in report or 'File not found' in report:
            raise FirmwareInputError(role + ': debugfs could not read image')
    else:
        _run_external([*prefix, '--extract=' + dest_path, source_path],
                      role + ' EROFS extraction')
    if not any(output.iterdir()):
        raise FirmwareInputError(role + ': filesystem contains no extractable files')
    prepared.roots[role] = output
    prepared.sources.append(dict(image=image.name, filesystem=kind, extracted_partition=role))


def _choose_partition(images: Path, role: str, slot: Optional[str]):
    choices = [role + ('_' + slot if slot else '') + '.img', role + '.img'] if slot else [role + '.img', role + '_a.img', role + '_b.img']
    for name in choices:
        file = images / name
        if file.is_file():
            return file
    return None


@contextmanager
def prepare_firmware(source: Path, *, allow_partial: bool = False,
                     auto_install: bool = True):
    """Normalize firmware bundle to boot images and extracted partition directories."""
    source = Path(source).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError('Firmware input does not exist: ' + str(source))
    with tempfile.TemporaryDirectory(prefix='tdtnext-firmware-') as tmp:
        work = Path(tmp)
        images = work / 'images'
        images.mkdir()
        prepared = PreparedFirmware(images=images)
        entries, chunks, total = {}, {}, [0]
        if source.is_dir():
            _stage_directory(source, images, entries, total, chunks)
            for role in FILESYSTEM_ROLES:
                direct = source / role
                if direct.is_dir() and not direct.is_symlink():
                    prepared.roots[role] = direct
        elif _archive_type(source):
            _stage_archive(source, images, entries, total, chunks)
        elif _canonical_image(source.name) or _sparsechunk_name(source.name):
            with source.open('rb') as stream:
                _write_image(stream, source.name, images, entries, total, chunks,
                             size_hint=source.stat().st_size)
        else:
            raise FirmwareInputError('Use a firmware directory, Motorola/Google ZIP, Samsung TAR/TAR.MD5, or *.img')
        _join_sparsechunks(images, entries, chunks, total)
        if not entries:
            raise FirmwareInputError('Firmware contains no supported recovery/boot/partition images')
        for name, info in sorted(entries.items()):
            prepared.sources.append(dict(image=name, **info))
        primary = None
        for role in BOOT_ROLES:
            primary = _choose_partition(images, role, None)
            if primary is not None:
                break
        if primary is None:
            raise FirmwareInputError('No boot/recovery/vendor_boot/init_boot image in firmware')
        slot_match = re.search(r'_([ab])\.img$', primary.name.lower())
        slot = slot_match.group(1) if slot_match else None
        super_image = _choose_partition(images, 'super', slot)
        if super_image is not None:
            try:
                _unpack_super(super_image, work, prepared, entries,
                              auto_install=auto_install)
            except FirmwareInputError as exc:
                prepared.blockers.append(str(exc))
                if not allow_partial:
                    raise
        for role in FILESYSTEM_ROLES:
            if role in prepared.roots:
                continue
            image = _choose_partition(images, role, slot)
            if image is None:
                continue
            try:
                _extract_partition(image, role, work, prepared,
                                   auto_install=auto_install)
            except FirmwareInputError as exc:
                prepared.blockers.append(str(exc))
                if not allow_partial:
                    raise
        if 'vendor' not in prepared.roots:
            prepared.blockers.append('No extracted vendor partition; firmware/HAL closure cannot be validated')
        prepared.warnings.append('A complete firmware package cannot prove recovery source buildability or safe boot')
        yield prepared


def write_firmware_audit(tree: Path, firmware: PreparedFirmware):
    path = Path(tree) / 'firmware-input-audit.json'
    path.write_text(json.dumps(firmware.audit(), indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return path
