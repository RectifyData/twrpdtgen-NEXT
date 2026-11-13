# twrpdtgen-NEXT

A modernized, safety-oriented evolution of twrpdtgen for generating TWRP
device-tree skeletons from classic and split Android boot images.

## Documentation

- **[Launcher guide](docs/launchers.md)** — complete Windows CMD, PowerShell,
  Linux and Google Colab setup/usage, command reference, examples and
  troubleshooting.
- **[Vendor-neutral Colab generation](docs/generic-colab.md)** — upload Android boot/recovery images from any supported OEM and generate a tree without Samsung FUS.
- **[Samsung cloud firmware slicing + generation](docs/cloud-firmware-slicing.md)** — download Samsung firmware from FUS in the cloud, return only one image, or continue directly into device-tree generation.
- Run `python3 -m twrpdtgen --help` (or the equivalent through a launcher) for
  the current generator CLI arguments.

## Android-friendly browser GUI

An additional full GUI runs locally in a mobile browser and works without
Tk or a desktop environment. On Android, start it inside Termux:

```bash
pkg install python git
python -m pip install git+https://github.com/RectifyData/twrpdtgen-NEXT.git
twrpdtgen-web
```

The local server binds only to `127.0.0.1:8765` and opens the browser.
If automatic opening is unavailable, visit `http://127.0.0.1:8765/`.
Use the phone's file picker to upload a boot/recovery image, ZIP/TAR archive,
or companion image directly into the local application; or specify an
existing Termux-accessible file path. Run the same generator and download the
ZIP directly in the browser when finished. The web GUI uses a per-session
token, rejects off-host requests, and has no cloud dependencies.

Termux may require access to shared storage (`termux-setup-storage`)
for manually typed paths. Android use depends on successfully installing
Python dependencies in your Termux environment; it is not an APK.

```bash
python -m twrpdtgen.webgui --port 8765
# Windows: launcher.cmd --web
# Linux:   ./launcher.sh --web
```

## Desktop GUI and independent CLI

Windows and Linux now have a full Tk GUI with file/folder and companion-image
pickers, recovery layout, TWRP profile and ramdisk settings, partition size
fields, ZIP output, live logs and a floating Tools menu. The GUI runs locally
and **never flashes a device**.

Windows: double-click `launcher.cmd`. Linux desktop: `./launcher.sh`.
Installed: `twrpdtgen-gui`.

The independent command line remains available without a desktop:

```bash
twrpdtgen-cli recovery.img -o output
python3 -m twrpdtgen recovery.img -o output
twrpdtgen-gui --source recovery.img
```

The GUI requires Python tkinter and a graphical desktop. Android Termux
can use the local browser GUI or CLI; Tk itself needs X11 on Android.

## Easy Mode — recommended standalone use

For normal use, you should not need to remember commands or type image names.

**Windows:** double-click `launcher.cmd`. NEXT opens its full GUI. Choose a
recovery/boot `.img`, a ZIP containing Android images, or cancel the file
picker to choose a folder. You can also drag an image, ZIP, or folder directly
onto `launcher.cmd`.

**Linux/desktop:** run `./launcher.sh` with no arguments. NEXT opens its full GUI
when a graphical desktop is available, or gives a drag-and-drop path prompt in
a terminal.

**Installed package:** run `twrpdtgen` or `twrpdtgen-easy` with no arguments.

Easy Mode automatically:

- recognizes standard recovery/boot image roles and A/B slot filenames;
- gathers matching nearby companion images when you select one standard image;
- accepts folders, ZIP archives, TAR/TAR.MD5/compressed TAR packages, `.img.lz4` payloads, and common factory archives with a nested image ZIP;
- ignores non-image ZIP contents and blocks unsafe ZIP paths;
- creates a portable device-tree ZIP automatically;
- avoids overwriting old output by choosing numbered output names;
- prints plain-language hints for common input/layout failures.

Advanced flags remain available through the normal CLI, but they are not
required for the common path.

## Modern Android image support

NEXT parses the AOSP image structures used by current Android releases:

- boot/recovery header v3 and v4
- init_boot.img v4 generic ramdisk, including standalone resource extraction
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

## Vendor-neutral Colab workflow

The core generator is OEM-neutral. For phones where you already have the
required recovery/boot images, use
**[colab/generic_image_to_tree.ipynb](colab/generic_image_to_tree.ipynb)**.

That notebook is now **upload-and-run**: select the images and NEXT automatically recognizes standard `recovery.img`, `boot.img`, `vendor_boot.img`, and `init_boot.img` names (including `_a` / `_b` slot variants), chooses the primary recovery source, adds companions, generates the tree, and downloads the symlink-safe ZIP. No image filenames need to be typed.

Samsung FUS support is an optional acquisition path, not a requirement of the
generator. See **[docs/generic-colab.md](docs/generic-colab.md)**.

The same zero-typing discovery is available from the command line:

~~~bash
python3 -m twrpdtgen.auto_tree ./images -o ./output --archive twrp-device-tree.zip --overwrite
~~~

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

Only the final payload is downloaded to the local machine in image-only mode.
The same Colab notebook can now continue directly into the rest of twrpdtgen:
it feeds the extracted recovery-bearing image into the normal DeviceTree
pipeline, generates the candidate source tree, ZIPs the
`<manufacturer>/<codename>/` output, and downloads only that ZIP.

~~~bash
python3 -m twrpdtgen.cloud_tree \
  -m SM-A207F \
  -r NEE \
  --partition recovery \
  --package AP \
  --tree-output /content/twrp-tree \
  --archive /content/twrp-device-tree.zip \
  --colab-download
~~~

The full firmware ZIP is deleted from the cloud by default after a successful
run.

The downloadable device-tree ZIP excludes `recovery/stock-root/` by default and
preserves Unix symlink metadata. The full stock extraction remains available in
the Colab workspace for audit; opt in with `--include-stock-root` only when it is
actually needed.

For the easiest workflow, open
**[colab/cloud_firmware_slice.ipynb](colab/cloud_firmware_slice.ipynb)** in
Google Colab. It now exposes **Generate TWRP device tree** and
**Extract image only** modes. See
**[docs/cloud-firmware-slicing.md](docs/cloud-firmware-slicing.md)** for the
architecture, generation options, package selection, cleanup behavior and
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

## Devices without a dedicated recovery partition

NEXT now extracts the generic ramdisk directly from `init_boot.img`.
When no dedicated recovery or identifiable vendor_boot recovery fragment exists,
auto mode can use init_boot as a **generic resource source**. When vendor_boot
provides an unambiguous recovery ramdisk, NEXT includes init_boot generic
resources below that vendor recovery ramdisk.

```bash
python3 -m twrpdtgen init_boot.img \
  --boot-image boot.img \
  --vendor-boot vendor_boot.img \
  --recovery-layout init_boot
```

The flag controls **extraction source**, not where TWRP must be flashed.
A generic init_boot ramdisk is not, by itself, a complete recovery image.
For a full tree, stock fstab and device identity still need to be available,
often from companion images. If those are absent, NEXT does not fabricate them.
To extract only without generating a tree:

```bash
python3 -m twrpdtgen init_boot.img --extract-only ./extracted-init
```

Verify actual recovery placement, kernel/vendor compatibility, AVB and
partition geometry independently before building/flashing.

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

NEXT hardcodes provisional boot/recovery (and modern init_boot/vendor_boot)
partition-size limits using the actual supplied image file length, rounded up
to a 4 KiB boundary. This avoids a blank recovery-size field even in cloud
firmware-slicing workflows.

**These are provisional minimum build limits, not verified physical partition
capacities.** A packed image may be smaller than its flash partition, and a
new TWRP image may grow larger than stock. Verify GPT/lpdump before flashing.
Verified `--boot-size` and `--recovery-size` overrides take precedence.
For known GPT/super geometry, supply the verified values when needed:

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
