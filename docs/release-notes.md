# twrpdtgen-NEXT 3.1.0a2 — Android 13–16 image extraction preview

This prerelease removes the earlier "skeleton only" limitation for modern
split boot layouts.

- Native parsing for AOSP boot/recovery header v3/v4.
- Android 13+ init_boot v4 generic-ramdisk extraction.
- vendor_boot v3/v4 parsing, DTB extraction, bootconfig extraction, and v4
  vendor ramdisk table support.
- PLATFORM, RECOVERY, DLKM and unnamed vendor ramdisk fragments.
- Combined boot + init_boot + vendor_boot metadata for tree generation.
- Safe newc CPIO extraction plus LZ4 legacy/frame support.
- Persistent \`--extract-only\` and \`--extract-to\` workflows with
  machine-readable \`manifest.json\`.
- Split-ramdisk property and recovery-fstab discovery.
- Synthetic header-v3/v4 regression fixtures; CI needs no proprietary firmware.

**Experimental source generator prerelease.** Image parser tests validate
container handling, not recovery bootability on physical hardware.
