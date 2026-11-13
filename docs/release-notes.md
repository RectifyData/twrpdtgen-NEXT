# twrpdtgen-NEXT 3.1.0a16 — zero-typing generic Colab

This prerelease removes the tedious filename-entry step from the generic
multi-device workflow.

Changes:

- Adds `python -m twrpdtgen.auto_tree` for automatic discovery of conventional
  Android recovery/boot images in a directory.
- Recognizes `recovery.img`, `vendor_boot.img`, `boot.img`, and
  `init_boot.img`, including `_a` and `_b` slot-suffixed names.
- Prefers a dedicated recovery image when available, then vendor_boot, boot, or
  init_boot, and automatically supplies the remaining detected images as
  companions.
- Rejects genuinely ambiguous same-rank firmware candidates instead of silently
  combining images from different builds.
- Reworks the generic Colab notebook into an upload-and-run flow: no image
  filenames are typed manually.
- Accepts multiple uploaded images in one picker and can extract .img files
  directly from an uploaded ZIP.
- Keeps only optional dropdown/boolean advanced controls; the default path needs
  no text entry.
- Adds Linux/Windows regression tests for discovery ordering, nested image
  discovery, ambiguity handling, and missing-input errors.
- CI now validates the automatic-discovery CLI.

This remains a source-tree generator. OEM-specific AVB, encryption, SELinux,
image wrapping, partition geometry, and hardware bring-up still require
target-device validation before flashing.
