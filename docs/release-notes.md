# twrpdtgen-NEXT 3.1.0a13 — generated-tree build audit fixes

This prerelease follows a second full static audit of the clean ~10.9 MB
Galaxy A20s SM-A207F generated tree.

Two additional generic defects were confirmed:

- The generated `recovery/root/` overlay existed on disk but the product
  makefile never copied it into the recovery ramdisk. Device-specific init,
  firmware, modules, or VINTF files selected by minimal mode could therefore be
  silently absent from the built recovery.
- The stock A20s recovery explicitly writes
  `/sys/class/backlight/panel0-backlight/brightness`, but NEXT discarded that
  directly observable device policy instead of wiring TWRP's brightness
  control to the same node.

Fixes in 3.1.0a13:

- Every generated product makefile now copies `recovery/root/` into
  `recovery/root` using `find-copy-subdir-files`, matching established TWRP
  device-tree practice.
- Brightness path/default are inferred only when stock init contains an
  unambiguous explicit `write .../brightness <number>`. Ambiguous multiple
  brightness nodes are deliberately left unset.
- TWRP is allowed to discover `max_brightness` at runtime; NEXT does not guess
  a maximum value.
- Generated READMEs now call out Samsung dedicated-recovery image
  trailer/Odin/verified-boot packaging as a device-specific verification item.
- Regression tests cover both recovery-overlay inclusion and stock-derived
  brightness policy.

The A20s audit still leaves target-specific bring-up work outside safe generic
generation: TWRP backup/flash fstab policy, external-SD/USB-OTG storage flags,
Qualcomm RTC/platform extras, cutout offsets, Samsung image trailer/Odin
packaging, and any touch firmware or custom USB/ueventd files absent from the
selected stock recovery. Those must be validated for the exact variant rather
than copied blindly from another A20s tree.

**Experimental source generator prerelease.** A generated tree remains a
build/bring-up candidate, not evidence that a recovery image is safe to flash.
