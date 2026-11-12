# twrpdtgen-NEXT 3.1.0a9 — full twrpdtgen in the Colab firmware workflow

This prerelease bundles the rest of twrpdtgen directly into the cloud-assisted
Samsung firmware notebook.

- Adds `twrpdtgen.cloud_tree`, an end-to-end firmware-to-device-tree pipeline.
- Downloads/decrypts Samsung firmware in the cloud through samloader-rs.
- Reuses the streamed Odin TAR.MD5 slicer and Samsung legacy/standard LZ4
  decoders from the cloud-slice workflow.
- Feeds the extracted recovery-bearing image directly into the normal
  `DeviceTree` generator without first downloading it to the user's PC.
- Exposes the normal skeleton, recovery-layout, recovery-root, recovery-fragment,
  and verified partition-size options.
- Packages the generated `<manufacturer>/<codename>/` hierarchy into a ZIP.
- Adds `--colab-download` to download only the final device-tree ZIP.
- Keeps the extracted image temporary by default; `--keep-image` and
  `--image-output` make it persistent when needed.
- Keeps the full firmware temporary by default; `--keep-firmware` remains an
  explicit opt-in.
- Updates the existing Colab notebook with two selectable modes:
  **Generate TWRP device tree** and **Extract image only**.
- The notebook now runs `launcher.sh --setup-only` during setup so legacy
  recovery parsing receives the same Linux host dependencies as normal
  twrpdtgen.
- Adds `twrpdtgen-cloud-tree` as a console entry point.
- Adds regression coverage for the one-download -> one-slice -> generation ->
  ZIP workflow and ZIP hierarchy.
- Makes reruns with `--overwrite` clean stale cloud firmware/image files before
  starting again.

The full cloud-tree path currently targets a single recovery-bearing primary
image. Split modern layouts that require coordinated boot/init_boot/vendor_boot
companions still use twrpdtgen's existing multi-image interface.

**Experimental source generator prerelease.** A generated source tree is not
proof that a recovery built from it is safe to flash. Kernel, fstab, AVB,
encryption, SELinux and target-specific hardware integration still require
validation.
