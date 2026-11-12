# twrpdtgen-NEXT 3.1.0a12 — legacy image fidelity and fstab safety

This prerelease follows inspection of a clean 3.1.0a11 Galaxy A20s
SM-A207F tree. The a11 packaging fixes are now confirmed in a real artifact:
the downloadable tree fell to about 10.9 MB, excluded audit-only
`recovery/stock-root/`, included `recovery.stock.fstab` and
`proprietary-files.txt`, used a minimal recovery overlay, and stamped the
generated README with the exact NEXT version.

That inspection exposed two remaining generic reconstruction problems:

- The extracted A20s prebuilt kernel is actually an `Image.gz-dtb`: a gzip
  kernel stream followed by an appended flattened device tree, while the
  generated BoardConfig still declared `BOARD_KERNEL_IMAGE_NAME := Image`.
- The normalized TWRP fstab discarded the stock userdata
  `length=-16384` reservation and kept a system-as-root source mount at
  `/`, losing recovery-relevant wipe geometry and the conventional
  `/system_root` TWRP mount.

Fixes in 3.1.0a12:

- Detects legacy prebuilt kernel format from content. Gzip kernels emit
  `Image.gz`; gzip kernels with an appended FDT emit `Image.gz-dtb`.
- Emits the detected kernel artifact through `BOARD_KERNEL_IMAGE_NAME`.
- Uses a NEXT-owned conservative TWRP fstab renderer that preserves
  `length=`, `logical`, `slotselect`, and `wait` flags.
- Maps stock `/` to `/system_root` when the parsed device is
  system-as-root, avoiding an empty `display=` entry.
- Keeps the exact stock fstab beside the normalized file for full audit.
- Adds notebook fields for verified boot, recovery, super, and dynamic-group
  partition sizes. They remain blank by default and are never guessed.
- Adds regression coverage for raw/gzip/gzip+DTB kernel identification and
  userdata footer preservation.

Target-specific recovery bring-up files that are not present in the selected
stock recovery ramdisk, such as additional USB init, ueventd permissions,
touch firmware, brightness policy, and variant-specific TWRP flags, remain
explicit device-validation work rather than unsafe generic guesses.

**Experimental source generator prerelease.** A generated tree is still not
proof of a bootable or safe-to-flash recovery.
