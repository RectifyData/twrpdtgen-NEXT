# SPDX-License-Identifier: Apache-2.0
"""Safe, OEM-neutral selection of vendor_boot v4 ramdisk fragments."""
from __future__ import annotations

from pathlib import Path
import hashlib


class VendorFragmentConflict(ValueError):
    pass


def fragment_label(fragment):
    return f"{fragment.index}:{fragment.name or '(unnamed)'}({fragment.type_name})"


def _file_signature(file):
    if file.is_symlink():
        return ('link', str(file.readlink()))
    digest = hashlib.sha256()
    with file.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return ('file', digest.hexdigest())


def conflicting_universal_fragments(fragments):
    """Avoid silently overwriting fstab/init/files between shared fragments."""
    seen, conflicts = {}, []
    for fragment in fragments:
        root = Path(fragment.root)
        if not root.is_dir():
            raise ValueError(f"Cannot inspect vendor fragment {fragment_label(fragment)}")
        for file in root.rglob('*'):
            if not file.is_file() and not file.is_symlink():
                continue
            rel = file.relative_to(root).as_posix()
            signature = _file_signature(file)
            if rel in seen and signature != seen[rel][0]:
                conflicts.append((rel, fragment_label(seen[rel][1]),
                                  fragment_label(fragment)))
            else:
                seen[rel] = (signature, fragment)
    return conflicts


def plan_untyped_vendor_fragments(fragments, *, allow_generic_fallback=False):
    """Return (unconstrained fragments, manifest); never guess board_id values.

    PLATFORM and NONE form the common base. DLKM is supplementary only.
    A conflicting set may fall back to init_boot only if that source exists.
    """
    candidates = [f for f in fragments if f.ramdisk_type in (0, 1, 3)]
    selected = [f for f in candidates if not any(f.board_id)]
    skipped = [f for f in candidates if any(f.board_id)]
    report = {
        'selected_fragments': [{
            'index': f.index, 'name': f.name, 'type': f.type_name,
            'board_id': list(f.board_id)} for f in selected],
        'skipped_board_specific_fragments': [{
            'index': f.index, 'name': f.name, 'type': f.type_name,
            'board_id': list(f.board_id)} for f in skipped],
        'warnings': [],
    }
    if skipped:
        report['warnings'].append(
            'Unmatched board-specific vendor ramdisks were excluded. '
            'Review board_id before treating this tree as device-ready.')
    conflicts = conflicting_universal_fragments(selected) if len(selected) > 1 else []
    if conflicts:
        report['conflicting_paths'] = [
            {'path': path, 'first': first, 'second': second}
            for path, first, second in conflicts[:40]]
        selected = []
        report['selected_fragments'] = []
        report['warnings'].append('Common vendor ramdisks conflict; not merged.')
    if not any(f.ramdisk_type in (0, 1) for f in selected):
        if allow_generic_fallback:
            selected = []
            report['selected_fragments'] = []
            report['warnings'].append(
                'Using init_boot generic ramdisk only; no shared vendor '
                'platform fragment could be proven.')
        else:
            raise VendorFragmentConflict(
                'No unambiguous shared vendor platform fragment. '
                'Select a verified --recovery-fragment or provide init_boot '
                'and matching vendor partition. Available: ' +
                ', '.join(fragment_label(f) for f in fragments))
    return selected, report
