# twrpdtgen-NEXT 3.1.0a8 — Samsung LZ4 + Colab error fix

This prerelease fixes a real failure found while extracting recovery from
Samsung Galaxy A20s SM-A207F / NEE firmware.

- Adds streaming support for Samsung/Android **legacy LZ4** payloads
  (magic `02 21 4c 18`) used by Odin firmware images such as
  `recovery.img.lz4`.
- Keeps standard LZ4 frame support (magic `04 22 4d 18`).
- Decodes legacy LZ4 in 8 MiB blocks without loading the entire image into
  memory, preserving the cloud-slicing design for large firmware payloads.
- Rejects truncated/invalid legacy blocks and unknown LZ4 magic with clear
  diagnostics.
- Changes the cloud slicer CLI to print a concise
  `[cloud-slice] ERROR: ...` message instead of an internal Python traceback
  for expected input/download/archive failures.
- Changes the Colab notebook to invoke the slicer directly, so a real failure
  reason is displayed instead of a generic outer `CalledProcessError`.
- Adds a synthetic Samsung legacy-LZ4 regression fixture.
- Live diagnostics confirmed that Samsung FUS metadata lookup and firmware
  transfer startup work for `SM-A207F / NEE`; the current version returned is
  `A207FXXS5CWF1/A207FOXM5CWD1/A207FXXS5CWD1/A207FXXS5CWF1`.
- Removes the temporary device-specific FUS probes from permanent CI after
  diagnosis.

**Experimental source generator prerelease.** The legacy-LZ4 extraction path is
CI-tested and the A20s FUS transfer was verified to start, but a complete
multi-gigabyte live firmware download is intentionally not part of CI.
