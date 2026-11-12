# twrpdtgen-NEXT 3.1.0a13 — recovery overlay build wiring

A static audit of the clean Galaxy A20s SM-A207F generated tree exposed a
critical source-tree integration bug: NEXT correctly generated
`recovery/root/`, but the product makefile never copied that overlay into the
recovery ramdisk.

For the inspected A20s tree this meant the generated
`init.recovery.qcom.rc` existed in the source ZIP but would not be present in a
built recovery image. The same bug affected every generated device that relied
on minimal/full recovery-root overlays.

Fixes in 3.1.0a13:

- Adds the standard Android/TWRP `find-copy-subdir-files` product rule so
  generated `recovery/root/` files are actually installed into
  `recovery/root` in the built image.
- Adds regression coverage that generated TWRP product makefiles wire the
  recovery overlay into the build.
- Clarifies generated README wording: `recovery/stock-root/` lives in the
  generation workspace and is intentionally omitted from exported cloud ZIPs
  unless explicitly requested.

The audit also confirmed several A20s-specific bring-up gaps that are not safe
to invent generically: exact recovery/boot partition sizes, Samsung/QCOM USB
recovery init, ueventd permissions, touch firmware, brightness/display policy,
TWRP storage/backup fstab policy, encryption/decryption, and AVB/SELinux
behavior.

**Experimental source generator prerelease.** A generated tree still requires
a real source build and hardware validation before flashing.
