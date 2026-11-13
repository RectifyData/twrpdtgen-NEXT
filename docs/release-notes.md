# twrpdtgen-NEXT 3.1.0a15 — vendor-neutral Colab and tree export

This prerelease makes NEXT's multi-device scope explicit and usable without
Samsung FUS while retaining the 3.1.0a14 stock-brightness and partition-size
fixes already present on master.

Changes:

- Adds `colab/generic_image_to_tree.ipynb`, a vendor-neutral Colab workflow for
  uploaded recovery/boot images from Samsung, Google, Xiaomi, OnePlus,
  Motorola, Sony, Nothing, ASUS, Fairphone and other Android devices supported
  by the parser.
- Supports dedicated `recovery.img`, recovery-as-boot, and split modern input
  sets with optional `boot.img`, `vendor_boot.img`, and `init_boot.img`.
- Adds `python -m twrpdtgen.tree_archive`, a generic generated-tree ZIP
  exporter that preserves Unix symlinks, enables ZIP64, and excludes
  `recovery/stock-root` by default.
- Refactors Samsung cloud-tree generation to use that same generic archiver, so
  ZIP behavior is no longer implemented inside Samsung-specific download code.
- Adds direct regression coverage using a non-Samsung `google/husky` tree.
- Adds notebook tests ensuring the generic workflow does not depend on
  samloader or a Samsung model.
- CI validates both Colab notebooks and the vendor-neutral tree-archive CLI.
- Adds documentation separating the OEM-neutral generator from Samsung-only
  FUS firmware acquisition.

The core generator is image-driven rather than phone-list-driven. OEM signing,
AVB, encryption, SELinux, display/input quirks, USB configuration, partition
geometry and OEM-specific image wrappers remain target-validation work and are
not guessed.

**Experimental source generator prerelease.** Generated trees still require a
real build and target-device validation before flashing.
