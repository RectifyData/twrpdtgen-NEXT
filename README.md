# twrpdtgen-NEXT

A modernized, safety-oriented evolution of
[twrpdtgen](https://github.com/twrpdtgen/twrpdtgen) for generating candidate
TWRP device-tree skeletons from classic and split Android boot images.

## Modern Android image support

NEXT parses the current AOSP boot-image structures used by Android 13–16:

- boot/recovery header v3 and v4
- \`init_boot.img\` v4 generic ramdisk
- \`vendor_boot.img\` v3 and v4
- vendor_boot v4 ramdisk tables, including PLATFORM, RECOVERY and DLKM fragments
- vendor DTB and v4 bootconfig extraction
- split-image composition: boot + init_boot + vendor_boot
- gzip, bzip2, XZ/LZMA, LZ4 frame, LZ4 legacy, and raw newc ramdisks
- Zstandard ramdisks when the host \`zstd\` command is installed

The CPIO extractor rejects parent/absolute paths and does not create device
nodes, sockets or FIFOs on the host. Image/table offsets are bounds-checked
before extraction.

### Extract only

\`\`\`bash
python3 -m twrpdtgen init_boot.img \
  --vendor-boot vendor_boot.img \
  --boot-image boot.img \
  --extract-only extracted-images
\`\`\`

The destination contains raw image components, expanded ramdisk roots, and
\`manifest.json\` with parsed header geometry and the vendor ramdisk table.

### Generate a modern device tree

\`\`\`bash
python3 -m twrpdtgen init_boot.img \
  --vendor-boot vendor_boot.img \
  --boot-image boot.img \
  --skeleton twrp-14.1
\`\`\`

If vendor_boot v4 contains a RECOVERY ramdisk fragment, NEXT prioritizes it for
recovery fstab discovery and identifies the recovery layout as \`vendor_boot\`.
Generic and vendor ramdisk properties are considered together instead of being
treated as one physical archive.

Use \`--extract-to DIR\` to keep parsed components while also generating a tree.

## Skeletons

| Mode | Product | Common config | Typical source |
|---|---|---|---|
| \`omni\` | \`omni_<codename>\` | \`vendor/omni/config/common.mk\` | legacy TWRP |
| \`twrp-12.1\` | \`twrp_<codename>\` | \`vendor/twrp/config/common.mk\` | TWRP 12.1 |
| \`twrp-14.1\` | \`twrp_<codename>\` | \`vendor/twrp/config/common.mk\` | TWRP 14.1 |
| \`auto\` | firmware SDK based | firmware SDK based | SDK >=34: 14.1; SDK 31–33: 12.1 |

## Installation

Requires Python 3.8 or later.

\`\`\`bash
python3 -m pip install .
python3 -m twrpdtgen --help
\`\`\`

The legacy AIK path may still require host tools such as \`cpio\`. Modern
vendor_boot/init_boot parsing is native Python except for optional Zstandard
decompression.

## Partition metadata

Partition sizes are never inferred from compressed image lengths. Supply
verified values from GPT/lpdump when needed:

\`\`\`bash
python3 -m twrpdtgen recovery.img \
  --super-size 9126805504 \
  --dynamic-group-size 9122611200
\`\`\`

Those values are illustrative only.

## What remains device-specific

Understanding the container format does not make a recovery automatically
bootable. TWRP still needs device-specific FBE/KeyMint/Gatekeeper integration,
SELinux policy, kernel modules, input/display quirks, AVB policy, and correct
repacking flags. \`vendor_kernel_boot\` and OEM-specific wrappers are separate
formats and are not silently treated as vendor_boot.

## Developer checks

\`\`\`bash
python3 -m compileall -q twrpdtgen tests
python3 -m unittest discover -s tests -v
\`\`\`

Generated trees and releases are source artifacts. They are not certified
flashable recovery images until built and tested for the target device.
