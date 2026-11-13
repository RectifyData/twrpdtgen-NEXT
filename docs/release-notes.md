# twrpdtgen-NEXT 3.1.0a28 — clean cloud slicer notebook

Source-only prerelease. Generated trees still require hardware validation.

- Removed orphaned variable references from the cloud firmware slicer's third
  **code** cell: keep-firmware, stock-root ZIP checkbox, extra image download,
  and undefined partition geometry fields. The stale "all broken" warning was
  removed as well.
- Restored the actual two-mode form: extract an image or generate a TWRP tree.
  Keep the existing image-only default; both paths run in fresh subprocesses.
- Split `tool_version` from optional Samsung `firmware_version` to prevent
  passing twrpdtgen's version to samloader as a firmware build number.
- Use `git pull` in the notebook setup cell, matching the Git updater UI.
- Validate subprocess completion and output-file existence before offering a
  browser download. Cleaned old execution numbers/outputs from committed cells.
- Updated notebook, documentation and automated tests to catch undefined
  configuration values and exercise both workflows.

Open the latest `colab/cloud_firmware_slice.ipynb` from master to obtain
these changes. This release does not include a bootable recovery image.
