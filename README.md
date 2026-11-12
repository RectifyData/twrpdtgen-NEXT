# twrpdtgen-NEXT

A modernized, safety-oriented evolution of twrpdtgen for generating TWRP
device-tree skeletons from classic and split Android boot images.

## Documentation

- **[Launcher guide](docs/launchers.md)** — complete Windows CMD, PowerShell,
  Linux and Google Colab setup/usage, command reference, examples and
  troubleshooting.
- **[Cloud firmware slicing](docs/cloud-firmware-slicing.md)** — use Google
  Colab/cloud compute to download Samsung firmware from FUS and return only the
  requested standalone partition image.
- Run `python3 -m twrpdtgen --help` (or the equivalent through a launcher) for
  the current generator CLI arguments.

## Modern Android image support

NEXT parses the AOSP image structures used by current Android releases:

- boot/recovery header v3 and v4
- init_boot.img v4 generic ramdisk
- vendor_boot.img v3 and v4
- vendor_boot v4 ramdisk tables with NONE, PLATFORM, RECOVERY and DLKM fragments
- vendor DTB and v4 bootconfig
- split boot + init_boot + vendor_boot input sets
- raw newc, gzip, bzip2, XZ/LZMA, LZ4 frame and Android legacy LZ4 ramdisks
- Zstandard ramdisks through the cross-platform Python zstandard decoder

The native parser is the default path. It reads each image once, validates
component/table bounds, expands the ramdisk once, and reuses that extraction for
device detection, fstab analysis and skeleton generation. This avoids a slower
unpack/repack/unpack pipeline while keeping the original image metadata in a
machine-readable manifest. When the generated output and extraction workspace
share a filesystem, stock-root uses hardlinks instead of rewriting every
regular file, with an automatic copy fallback across filesystems.

## Cloud-assisted Samsung firmware slicing

Need one small Samsung firmware image without pulling the full multi-gigabyte
firmware bundle through your local PC? NEXT can offload the heavy transfer and
decryption to Google Colab.

The cloud slicer uses samloader-rs for Samsung FUS download/decryption, streams
the selected Odin TAR.MD5 package without unpacking the whole AP archive, and
decodes the requested .lz4 payload directly into the final image.

~~~bash
python3 -m twrpdtgen.cloud_slice fetch \
  -m SM-G975F \
  -r BTU \
  --partition boot \
  -o /content/boot.img \
  --colab-download
~~~

Only the final payload is downloaded to the local machine. The full firmware
ZIP is deleted from the cloud by default after a successful slice.

For the easiest workflow, open
**[colab/cloud_firmware_slice.ipynb](colab/cloud_firmware_slice.ipynb)** in
Google Colab. See
**[docs/cloud-firmware-slicing.md](docs/cloud-firmware-slicing.md)** for the
architecture, package selection, exact-member mode, cleanup behavior and
limitations.

## Recovery ramdisk -> skeleton

A generated skeleton now comes from the **actual selected recovery ramdisk**,
not from a few copied init scripts.

Every generated tree contains:

- **recovery/stock-root/** — the full expanded selected stock recovery payload.
- **recovery/root/** — the files that Android/TWRP will overlay into its built
  recovery ramdisk.
- **recovery/ramdisk-manifest.json** — source image/fragment, extraction policy,
  copied files, symlinks and skipped special entries.

The full stock-root is ignored by the generated .gitignore so a generated
device-tree repository does not accidentally commit an entire stock recovery
filesystem. The manifest and actual recovery/root overlay remain trackable.

Selection is deterministic:

1. A supplied dedicated recovery.img is preferred for a dedicated layout.
2. On vendor_boot v4, a single typed RECOVERY fragment is selected directly.
3. Multiple RECOVERY fragments are not guessed because board_id encoding is
   vendor-defined. Select one by fragment name or index with
   --recovery-fragment.
4. Recovery-as-boot uses the actual boot ramdisk.
5. A v3 or merged vendor_boot ramdisk is accepted only when the source is
   unambiguous.

Auto mode always keeps the complete selected payload in stock-root and seeds a
conservative device-specific overlay into recovery/root. This applies even to a
typed RECOVERY fragment: the stock recovery binary and generic stock init must
not replace TWRP's own recovery implementation. Use --recovery-root-mode full
only when an exact full overlay is intentionally required.

Advanced override:

~~~bash
python3 -m twrpdtgen recovery.img --recovery-root-mode full
python3 -m twrpdtgen recovery.img --recovery-root-mode minimal
~~~

## Extract modern images only

~~~bash
python3 -m twrpdtgen init_boot.img \
  --vendor-boot vendor_boot.img \
  --boot-image boot.img \
  --extract-only extracted-images
~~~

The destination contains the raw image components, expanded ramdisk roots and
manifest.json with parsed header geometry and vendor ramdisk entries.

## Generate a modern device tree

~~~bash
python3 -m twrpdtgen init_boot.img \
  --vendor-boot vendor_boot.img \
  --boot-image boot.img \
  --skeleton twrp-14.1
~~~

If a vendor_boot has more than one recovery fragment:

~~~bash
python3 -m twrpdtgen init_boot.img \
  --vendor-boot vendor_boot.img \
  --boot-image boot.img \
  --recovery-fragment recovery \
  --skeleton twrp-14.1
~~~

The selector may also be a numeric vendor ramdisk table index.

## Skeleton profiles

| Mode | Product | Common config | Typical source |
|---|---|---|---|
| omni | omni_<codename> | vendor/omni/config/common.mk | legacy TWRP |
| twrp-12.1 | twrp_<codename> | vendor/twrp/config/common.mk | TWRP 12.1 |
| twrp-14.1 | twrp_<codename> | vendor/twrp/config/common.mk | TWRP 14.1 |
| auto | firmware SDK based | firmware SDK based | SDK >=34: 14.1; SDK 31–33: 12.1 |

## Google Colab

Clone the repository and run the root launcher. The launcher detects Colab,
installs only missing Linux extraction tools, installs NEXT from the clone, and
then forwards arguments to the normal CLI.

~~~bash
!git clone https://github.com/RectifyData/twrpdtgen-NEXT.git
%cd twrpdtgen-NEXT
!bash launcher.sh
~~~

After uploading an image that contains the recovery ramdisk, the normal form is:

~~~bash
!./launcher.sh /content/recovery.img -o /content/output
~~~

The `-o` / `--output` directory is created automatically when it does not
exist. The same syntax works for recovery-as-boot images when the correct
recovery layout is detected or supplied.

For a modern split GKI layout:

~~~bash
!bash launcher.sh /content/init_boot.img \
  --boot-image /content/boot.img \
  --vendor-boot /content/vendor_boot.img \
  --skeleton twrp-14.1 \
  -o /content/output
~~~

The no-argument form performs setup plus an environment check and prints the
ready-to-run examples. Useful launcher-only commands are
`--doctor`, `--self-test`, and `--setup-only`. All other arguments are
passed unchanged to `python3 -m twrpdtgen`.

See **[docs/launchers.md](docs/launchers.md)** for the full Colab/Linux launcher
reference, recovery-layout examples, output structure and troubleshooting.

## Windows

Windows now has a native CMD launcher for the modern parser path. From a normal
Command Prompt or PowerShell window:

~~~bat
git clone https://github.com/RectifyData/twrpdtgen-NEXT.git
cd twrpdtgen-NEXT
launcher.cmd "C:\firmware\recovery.img" -o "C:\twrp\output"
~~~

The output directory is created automatically. Split modern layouts use the
same arguments as Linux/Colab:

~~~bat
launcher.cmd "C:\firmware\init_boot.img" ^
  --boot-image "C:\firmware\boot.img" ^
  --vendor-boot "C:\firmware\vendor_boot.img" ^
  -o "C:\twrp\output"
~~~

The Windows launcher installs Python dependencies only when they are missing
and otherwise runs directly from the cloned source tree. Modern boot/recovery
header v3/v4, init_boot v4 and vendor_boot v3/v4 are handled without WSL.
Zstandard is decoded in Python, so a separate zstd.exe is not required.

Older image formats that fall back to the legacy AIK toolchain can still require
Linux/WSL. Also, preserving actual filesystem symlinks on Windows may require
Developer Mode or administrator privileges; the parser still rejects unsafe
escaping symlinks.

See **[docs/launchers.md](docs/launchers.md)** for the full Windows CMD and
PowerShell guide, including quoting rules, split-image examples and
troubleshooting.

## Installation

Requires Python 3.8 or later.

~~~bash
python3 -m pip install .
python3 -m twrpdtgen --help
~~~

The legacy AIK path can still require host tools such as cpio. The modern
boot/init_boot/vendor_boot parser and its supported compression formats are
Python-native on Windows, Linux and Colab.

## Partition metadata

Partition sizes are never inferred from compressed image lengths. Supply
verified GPT/lpdump values when needed:

~~~bash
python3 -m twrpdtgen recovery.img \
  --super-size 9126805504 \
  --dynamic-group-size 9122611200
~~~

Those numbers are illustrative only.

## What remains device-specific

Correct ramdisk extraction and placement does not make every generated recovery
bootable. FBE/KeyMint/Gatekeeper integration, SELinux, kernel modules,
input/display quirks, AVB policy and OEM-specific image wrappers still require
target-specific validation.

## Developer checks

~~~bash
python3 -m compileall -q twrpdtgen tests
python3 -m unittest discover -s tests -v
~~~

Generated trees and source releases are not certified flashable recovery
images until built and tested for the target device.
