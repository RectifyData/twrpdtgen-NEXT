# twrpdtgen-NEXT 3.1.0a14 — stock brightness policy

The A20s generated-tree audit continued after 3.1.0a13 fixed recovery-overlay
installation.

The inspected SM-A207F stock recovery contains an explicit init write to
`/sys/class/backlight/panel0-backlight/brightness` with value `200`. That
device-specific recovery policy was directly observable but NEXT previously
discarded it, leaving TWRP to locate a brightness node on its own.

Fixes in 3.1.0a14:

- Scans selected stock recovery init RC files for explicit
  `write .../brightness <number>` commands.
- Emits `TW_BRIGHTNESS_PATH` only when exactly one stock brightness node is
  unambiguous, and emits `TW_DEFAULT_BRIGHTNESS` only when startup actions
  agree on one positive value.
- Does not guess `TW_MAX_BRIGHTNESS`; TWRP can read the sibling
  `max_brightness` node at runtime and already has a fallback.
- Ignores shutdown/property-triggered values when choosing a startup default,
  and refuses to select between multiple different brightness paths.
- Generated READMEs now explicitly warn Samsung dedicated-recovery users that
  image trailer, Odin tar, and verified-boot packaging remain device-specific.
- Adds regression coverage for root and nested init RC brightness detection and
  rendered BoardConfig output.

The audit still leaves A20s-specific work that cannot be safely inferred from
this recovery image alone: TWRP backup/flash fstab policy, removable
microSD/USB-OTG flags, Qualcomm RTC/platform extras, cutout offsets, Samsung
image trailer/Odin packaging, and any custom USB/ueventd/touch-firmware files
not present in stock recovery.

**Experimental source generator prerelease.** Build and hardware validation are
still required before flashing.
