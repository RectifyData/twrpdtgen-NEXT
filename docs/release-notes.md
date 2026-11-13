# twrpdtgen-NEXT 3.1.0a19 — init_boot resource extraction

This is a source-only prerelease adding init_boot support for devices without
dedicated recovery partitions.

- Auto or explicit --recovery-layout init_boot selects generic init_boot
  resources when no dedicated/known recovery source exists.
- Split GKI recovery trees now preserve init_boot generic ramdisk resources
  beneath an unambiguous vendor_boot RECOVERY fragment.
- boot.img with no ramdisk may fall back to matching init_boot generic resources.
- Recognizes slot-suffixed recovery_a/b and init_boot_a/b image files.
- Adds regression coverage for layout detection, fallback, source merging,
  and proper attribution of generic vs recovery ramdisks.

Generic init_boot does NOT establish where a flashable TWRP image belongs.
An init_boot-only tree requires usable device properties and a stock fstab.
Build success, flash safety, AVB, encryption and actual bootability require
physical device-specific verification.
