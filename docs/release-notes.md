# twrpdtgen-NEXT 3.1.0a17 — beginner-friendly standalone Easy Mode

This prerelease makes the standalone tool usable without memorizing CLI syntax.

Changes:

- Running `twrpdtgen` with no arguments now launches Easy Mode.
- Windows `launcher.cmd` opens Easy Mode on double-click; drag-and-drop image,
  ZIP, and folder inputs are supported.
- Local Linux `launcher.sh` opens Easy Mode when run interactively with no
  arguments, while Colab/non-interactive setup behavior remains unchanged.
- Adds a native graphical file/folder picker when Tk is available, with a
  terminal drag-and-drop prompt as fallback.
- Accepts a folder, a single Android `.img`/`.img.lz4`, a ZIP, or TAR/TAR.MD5
  firmware packages.
- Standard image selections automatically collect nearby matching
  `recovery.img`, `boot.img`, `vendor_boot.img`, and `init_boot.img`
  companions, including A/B slot variants.
- Arbitrarily named single `.img` files are accepted as explicit primary
  images instead of forcing a rename.
- Archive handling extracts only useful recovery/boot `.img`/`.img.lz4`
  members, decodes standard and Samsung legacy LZ4 automatically, avoids
  expanding huge unrelated system/vendor images, and rejects duplicate image
  basenames that could mix firmware builds.
- Existing output is protected by automatic numbered filenames instead of
  silent replacement.
- Folder and ZIP paths can be passed directly to the main `twrpdtgen` CLI,
  and standard image names automatically use the companion-discovery path.
- Adds `twrpdtgen-easy` and `twrpdtgen-auto` console entry points.
- Adds regression coverage for drag/drop quoting, ZIP safety, output
  collision avoidance, companion discovery, and arbitrary image names.
- CI validates the Easy Mode CLI on Linux and the existing Windows regression
  suite exercises the updated launcher.

Easy Mode reduces user error but does not fabricate device-specific AVB,
encryption, SELinux, partition geometry, or OEM image-wrapper details. Generated
trees still require build and target-device validation before flashing.
