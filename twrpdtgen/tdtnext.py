# Copyright (C) 2026 The twrpdtgen-NEXT contributors
# SPDX-License-Identifier: Apache-2.0
"""Stock firmware to recovery source tree pipeline shared with the CLI.

Can be called directly as a library or through `tdtnext --input ... --output ...`.
"""
from __future__ import annotations

from pathlib import Path
import shutil

from twrpdtgen.firmware_input import prepare_firmware, write_firmware_audit


def run_firmware_job(input_path: Path, output: Path, *, allow_partial: bool = False,
                     overwrite: bool = False, skeleton: str = 'auto',
                     recovery_layout: str = 'auto', recovery_root_mode: str = 'auto',
                     recovery_fragment=None, boot_size=None, recovery_size=None,
                     super_size=None, dynamic_group_size=None, skeleton_only=False,
                     auto_install: bool = True):
    """Produce an audited device tree and portable ZIP from a stock firmware package.

    Extraction is streamed to a temporary directory, not the user's source.
    A tree is *not* automatically considered build-ready, flashable or bootable.
    """
    input_path = Path(input_path).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError('Firmware input does not exist: ' + str(input_path))
    if input_path.is_dir() and (output == input_path or output.is_relative_to(input_path)):
        raise ValueError('Output must differ from firmware input and cannot be inside its folder')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'twrp-device-tree.zip'
    if archive.exists() and not overwrite:
        raise FileExistsError('Archive already exists; pass --overwrite: ' + str(archive))
    from twrpdtgen.auto_tree import generate_from_directory
    from twrpdtgen.tree_archive import archive_tree
    print('Inspecting stock firmware: ' + str(input_path), flush=True)
    with prepare_firmware(input_path, allow_partial=allow_partial,
                          auto_install=auto_install) as firmware:
        print('Found ' + str(len(firmware.sources)) + ' firmware records; '
              + str(len(firmware.roots)) + ' extracted filesystem roots', flush=True)
        _, tree, _ = generate_from_directory(
            firmware.images, output, None, skeleton=skeleton,
            recovery_layout=recovery_layout,
            recovery_root_mode=recovery_root_mode,
            recovery_fragment=recovery_fragment, boot_size=boot_size,
            recovery_size=recovery_size, super_size=super_size,
            dynamic_group_size=dynamic_group_size, overwrite=overwrite,
            vendor_root=firmware.roots.get('vendor'),
            odm_root=firmware.roots.get('odm'),
            partition_roots=firmware.roots,
            complete=not skeleton_only,
        )
        # Separate DTBO may be absent from the boot/recovery image itself.
        # Include original partition payload for source inspection, but do not
        # infer AVB signing keys, image-size limits or boot compatibility.
        for role in ('dtbo', 'vbmeta', 'vbmeta_system', 'vbmeta_vendor'):
            original = firmware.images / (role + '.img')
            if not original.is_file():
                continue
            target = Path(tree) / 'prebuilt' / original.name
            if target.exists():
                if not __import__("filecmp").cmp(original, target, shallow=False):
                    firmware.warnings.append('Conflicting embedded and standalone ' + original.name)
            else:
                target.parent.mkdir(exist_ok=True)
                shutil.copy2(original, target)
        write_firmware_audit(tree, firmware)
        # Unresolved board-specific resources are important to surface even
        # when the candidate source tree is successfully generated.
        import json
        report_path = Path(tree) / 'generation-report.json'
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding='utf-8'))
            source = report.get('ramdisk_source', {})
            for warning in source.get('warnings', []):
                print('[tdtnext] WARNING: ' + warning, flush=True)
            if source.get('kind') == 'init_boot_generic_with_unresolved_vendor_fragments':
                print('[tdtnext] WARNING: Generic-only candidate. The selected '
                      'vendor_boot board variant remains unknown. Do not flash.',
                      flush=True)
        print('Creating source archive (recovery image is not built)', flush=True)
        # Package after writing the firmware provenance manifest.
        archive_tree(tree, archive, include_stock_root=False)
        return Path(tree), archive
