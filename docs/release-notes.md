# twrpdtgen-NEXT 3.1.0a7 — cloud firmware slicing

This prerelease implements cloud-assisted partial Samsung firmware extraction
for users who need one payload without downloading the full firmware bundle to
their local machine.

- Adds `twrpdtgen.cloud_slice` with `fetch` and `slice` workflows.
- Uses topjohnwu/samloader-rs for official Samsung FUS download/decryption.
- Auto-bootstraps the matching samloader-rs release when it is not installed,
  and requires/verifies GitHub's published SHA-256 asset digest before running
  the downloaded executable.
- Streams AP/BL/CP/CSC/HOME_CSC/USERDATA TAR.MD5 packages directly from the
  decrypted firmware ZIP instead of unpacking full multi-gigabyte TAR trees.
- Extracts only the requested payload and decodes Samsung LZ4 image members
  directly into the final standalone file.
- Adds package-aware selection so AP, CP, BL, and CSC payloads are searched in
  the likely package first.
- Deletes the full cloud firmware ZIP by default after a successful slice.
- Adds `--keep-firmware`, `--work-dir`, `--package`, `--member`,
  `--overwrite`, `--threads`, exact firmware `--version`, and
  `--colab-download` controls.
- Prints output size and SHA-256 for the final payload.
- Adds the `twrpdtgen-cloud-slice` console entry point and root
  `cloud-slice.sh` launcher.
- Adds a one-click Google Colab notebook at
  `colab/cloud_firmware_slice.ipynb`.
- Adds synthetic regression tests for streamed TAR.MD5 extraction, LZ4 decode,
  raw payload copy, package filtering, overwrite protection, and samloader
  release selection.
- Adds full documentation in `docs/cloud-firmware-slicing.md`.

This implementation extracts direct Odin-package members. It does not yet run a
second lpunpack stage for logical partitions nested inside super.img.

**Experimental source generator prerelease.** The slicing pipeline is covered by
synthetic CI tests, but Samsung FUS availability and live firmware contents are
external dependencies. Do not treat an extracted payload as safe to flash on a
different model, bootloader revision, or partition layout.
