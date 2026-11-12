# twrpdtgen-NEXT 3.1.0a3 — recovery-ramdisk skeleton generation

This prerelease changes skeleton generation to use the selected recovery
ramdisk itself rather than copying only a few init scripts.

- Preserves the complete expanded selected recovery payload in
  `recovery/stock-root/`.
- Seeds the actual Android/TWRP build overlay in `recovery/root/`.
- Typed vendor_boot v4 RECOVERY fragments are copied in full because AOSP
  builds those fragments directly from the recovery staging root.
- Complete stock recovery/boot ramdisks use a conservative auto overlay so
  stock recovery, init, adbd and generic framework files do not replace TWRP.
- Adds deterministic `--recovery-fragment` selection when vendor_boot has
  multiple board-specific recovery fragments; unsafe board_id guessing is
  rejected.
- Adds `--recovery-root-mode auto|minimal|full`.
- Recovery fstab selection now follows the selected recovery source first.
- Dedicated recovery.img takes precedence over a companion vendor_boot hint.
- Adds `recovery/ramdisk-manifest.json` with source and copy provenance.
- Ramdisk tree copying preserves safe relative symlinks and rejects escaping
  symlink targets/special host entries.
- Adds regression coverage for stock-root preservation, minimal/full overlay
  behavior and vendor recovery-fragment selection.

**Experimental source generator prerelease.** Recovery-root extraction and
skeleton placement are validated by tests, but physical-device bootability
still depends on device-specific kernel, AVB, SELinux and decryption support.
