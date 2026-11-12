# twrpdtgen-NEXT 3.1.0a10 — generated-tree integrity fixes

This prerelease is based on a direct inspection of a generated Galaxy A20s
SM-A207F tree from the full Colab workflow.

Verified generator fixes:

- Replaces the generic `shutil.make_archive` cloud ZIP path with a ZIP writer
  that preserves Unix symlink entries instead of dereferencing them into regular
  files.
- Excludes `recovery/stock-root/` from the downloadable device-tree ZIP by
  default. The complete stock extraction remains in the cloud workspace for
  audit and can be included explicitly with `--include-stock-root`.
- Adds the Colab `include_stock_root_in_zip` control and a prominent warning
  when `recovery_root_mode = full` is selected.
- Preserves the exact input fstab as `recovery.stock.fstab` beside the
  normalized TWRP `recovery.fstab`.
- Generates a documented placeholder `proprietary-files.txt` so the generated
  extraction helper scripts no longer reference a nonexistent local file.
- Fixes an inverted BoardConfig template condition: 64-bit devices now emit
  `TARGET_USES_64_BIT_BINDER := true` instead of emitting it only for
  non-64-bit targets.
- Preserves legacy boot-header reconstruction metadata already extracted by
  AIK: board name, page size, kernel offset and DTB offset are now emitted back
  into BoardConfig/mkbootimg arguments when present.
- Adds regression tests for symlink-safe ZIP packaging, stock-root exclusion,
  optional stock-root inclusion, stock-fstab preservation, the proprietary-file
  placeholder, and 64-bit binder output.

The inspected A20s artifact also exposed target-specific items that remain
verification tasks rather than safe generic auto-fixes, including bootloader
board-name selection and TWRP fstab policy/flags.

**Experimental source generator prerelease.** A generated tree still requires
device-specific build and boot validation before it is trusted on hardware.
