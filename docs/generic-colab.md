# Vendor-neutral Colab generation

The core twrpdtgen-NEXT generator is not Samsung-specific. The Samsung FUS
notebook is only a convenience downloader for Samsung firmware.

Use **colab/generic_image_to_tree.ipynb** when you already have the relevant
Android boot/recovery images from any manufacturer.

## Supported input layouts

Classic devices normally use one dedicated recovery image:

```
recovery.img
```

Recovery-as-boot devices can use a boot image as the primary input.

Modern split layouts may use a primary image plus companions:

```
init_boot.img
boot.img
vendor_boot.img
```

The exact set depends on where that device stores the recovery ramdisk.

## Workflow

1. Run the setup cell. It pulls the current repository and prints the exact
   NEXT version and Git commit.
2. Upload all required images with the upload cell.
3. Enter the uploaded filenames in the generation form.
4. Leave optional companion names blank when they are not used by that device.
5. Leave partition-size fields blank unless the values were verified from GPT,
   lpdump, or equivalent authoritative partition metadata.
6. Run generation. The notebook launches the generator in a fresh Python
   process, discovers the single generated manufacturer/codename tree, bundles
   it with the vendor-neutral tree archiver, and downloads the resulting ZIP.

The ZIP preserves POSIX symlink metadata and omits `recovery/stock-root` by
default. Enable stock-root inclusion only for auditing.

## What is actually generic

Manufacturer and codename come from the supplied image properties. Architecture,
boot-header geometry, ramdisk compression, recovery layout, fstab analysis,
system-as-root handling, dynamic-partition hints, and image components are
derived from the images rather than from a hardcoded phone list.

That means the same path can be used for Samsung, Google, Xiaomi, OnePlus,
Motorola, Sony, Nothing, ASUS, Fairphone and other Android devices when their
image format is supported.

## What remains device-specific

A generated tree is still a bring-up starting point. Depending on the device,
you may still need verified work for:

- AVB signing and rollback policy
- file-based encryption / metadata encryption
- KeyMint, Gatekeeper and decryption services
- SELinux
- kernel modules
- display, brightness, touch and input quirks
- USB gadget configuration
- OEM-specific boot/recovery image wrappers or trailers
- exact partition geometry
- vendor-specific build flags

NEXT deliberately avoids inventing those values.
