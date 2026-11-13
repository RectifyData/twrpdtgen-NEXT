# Launcher guide

twrpdtgen-NEXT ships two launchers that expose the same generator CLI on the
platforms where they run:

- `launcher.sh` — Google Colab and Debian/Ubuntu Linux.
- `launcher.cmd` — native Windows Command Prompt and PowerShell.

Both launchers bootstrap the dependencies they need and then forward normal
arguments to `python -m twrpdtgen`.

## Android and browser GUI

`twrpdtgen-web` or `python -m twrpdtgen.webgui` runs a local-only mobile
and desktop browser interface, bound to 127.0.0.1:8765. On Android/Termux,
the web GUI uses the system browser and file picker without needing Tk/X11.
It accepts image/archive/folder paths or local file uploads, matching
companions, advanced generator settings and downloadable ZIP output.

Android Termux:
```sh
pkg install python git
python -m pip install git+https://github.com/RectifyData/twrpdtgen-NEXT.git
twrpdtgen-web
```
Use `termux-setup-storage` if you need manually typed shared-storage paths.
The server is private to this device, cannot be accessed remotely, and
does not send firmware to any web provider. It is a Python/Termux tool, not
a native Android APK. Installation of dependencies may vary by device.

## One option schema for desktop, Android/browser GUI, and CLI

All interfaces now use `twrpdtgen.main.build_parser()` for generator option
definitions. New standard CLI flags automatically appear under
**CLI options (automatically synchronized)** in both graphical interfaces,
and changes to choice lists update both. The localhost browser retrieves the
schema from `GET /api/options`.

Both GUIs parse values with the shared argparse parser and call the same
`execute_cli_job` implementation used by terminal invocation.
If a future CLI argument has an unsupported structure, automated regression
checks fail rather than silently dropping functionality. Extend the adapter
for such actions before publishing.

## v3.1.0a25 update availability and UI

The desktop UI has three focused PyQt5 tabs: **Build tree**, **Advanced
settings**, and **Updates**. Git update state is visible on the Updates tab.
The action starts disabled and only becomes available after a successful
check confirms a clean, behind-only tracking branch. It remains disabled
when current, ahead, diverged, dirty, or when Git is unavailable.

The Tk fallback and Android browser GUI enforce the same check-first rule.
Running `twrpdtgen-update --apply` when already up to date exits with an
explicit informative error rather than implying that an update happened.
No Git merge or checkout runs in that case.

## PyQt5 desktop GUI and safe Git updater

PyQt5 is the preferred desktop GUI when installed; Tk remains the fallback.
Install the optional dependency with `python -m pip install -e '.[qt]'`
from a checkout, then start `twrpdtgen-qt` or `twrpdtgen-gui`.
Force the Tk fallback with `twrpdtgen-gui --tk`.
Both desktop GUIs show source selection, options synced with CLI, and Git
update buttons. The Windows launcher attempts optional PyQt5 installation
with visible pip progress before starting GUI mode.

The standalone Git updater is `twrpdtgen-update`, or:

```sh
twrpdtgen-update --check
twrpdtgen-update --apply
./launcher.sh --check-updates
./launcher.sh --update
```

Windows: `launcher.cmd --check-updates` / `launcher.cmd --update`.
The Android localhost browser GUI also offers check/update controls.

The updater requires an actual Git checkout, a configured upstream branch,
no changed or untracked files, and no divergent local commits. It only
fast-forwards after an explicit choice. It never silently changes source,
executes a destructive reset, or modifies device partitions. A pip wheel
without the `.git` checkout cannot update itself via Git; clone the project
or use regular package upgrade mechanisms. Restart after a successful update.

## GUI and CLI entry points

Windows GUI: `launcher.cmd` or `launcher.cmd --gui`.
Linux GUI: `./launcher.sh --gui` (or no args on a graphical desktop).
Installed GUI: `twrpdtgen-gui --source recovery.img`.

The GUI supports image/companion selection, tree + ZIP or component extraction,
recovery/ramdisk options, verified partition sizes, visible logs, safe unique
ZIP filenames, Open Output and floating Tools menus.

CLI is still independent:
`twrpdtgen-cli IMAGE -o OUTPUT [OPTIONS]`, or
`python -m twrpdtgen IMAGE -o OUTPUT [OPTIONS]`.
Windows `launcher.cmd IMAGE -o OUTPUT` uses CLI; `launcher.cmd --cli`
opens terminal help. GUI cannot prove that a TWRP image is flash-safe.

## Easiest standalone use

For the common path, do not type the long commands shown later in this guide.

### Windows

Double-click `launcher.cmd`. NEXT opens the graphical application. Choose:

- a recovery/boot `.img`;
- a Samsung/Odin-style `.img.lz4`;
- a ZIP containing Android images;
- a TAR/TAR.MD5/compressed TAR package containing recovery/boot images;
- a common factory archive containing one nested image ZIP; or
- a folder containing the images.

You can also drag one of those files/folders directly onto `launcher.cmd`.
When one standard image is selected, NEXT automatically looks for matching
nearby companions such as `boot.img`, `vendor_boot.img`, and
`init_boot.img`. A/B slot selection is kept on the chosen slot instead of
mixing `_a` and `_b` companions.

The Windows launcher stays open after Easy Mode finishes so the output path or
error remains visible.

### Linux desktop/terminal

Run:

~~~bash
./launcher.sh
~~~

A graphical picker is used when available. Otherwise NEXT gives a terminal
prompt where a file/folder path can be pasted or dragged in.

### Installed Python package

Run either:

~~~bash
twrpdtgen
~~~

or:

~~~bash
twrpdtgen-easy
~~~

With no arguments, both enter Easy Mode.

Easy Mode protects previous work by creating numbered output names instead of
silently overwriting it. It also extracts only recovery/boot-related images
from large firmware archives when standard filenames are present, avoiding a
pointless full system/vendor extraction.

## Quick start

### Google Colab

~~~bash
!git clone https://github.com/RectifyData/twrpdtgen-NEXT.git
%cd twrpdtgen-NEXT
!./launcher.sh /content/recovery.img -o /content/output
~~~

### Linux

~~~bash
git clone https://github.com/RectifyData/twrpdtgen-NEXT.git
cd twrpdtgen-NEXT
./launcher.sh ~/firmware/recovery.img -o ~/twrp-output
~~~

### Windows Command Prompt

~~~bat
git clone https://github.com/RectifyData/twrpdtgen-NEXT.git
cd twrpdtgen-NEXT
launcher.cmd "C:\firmware\recovery.img" -o "C:\twrp-output"
~~~

### Windows PowerShell

~~~powershell
git clone https://github.com/RectifyData/twrpdtgen-NEXT.git
Set-Location twrpdtgen-NEXT
.\launcher.cmd "C:\firmware\recovery.img" -o "C:\twrp-output"
~~~

## General syntax

Linux/Colab:

~~~bash
./launcher.sh IMAGE -o OUTPUT [OPTIONS]
~~~

Windows:

~~~bat
launcher.cmd IMAGE -o OUTPUT [OPTIONS]
~~~

`IMAGE` is the primary image supplied to the generator. It may be a dedicated
`recovery.img`, a recovery-as-boot `boot.img`, `init_boot.img`, or
`vendor_boot.img`, depending on the device layout.

`-o` / `--output` is the **output parent directory**. It is created
automatically when necessary. The final generated device tree is written under:

~~~text
OUTPUT/<manufacturer>/<codename>/
~~~

For example, if the detected manufacturer is `samsung`, the codename is
`beyond2lte`, and `-o C:\twrp-output` is used, the final tree is:

~~~text
C:\twrp-output\samsung\beyond2lte\
~~~

## Which image should I pass?

| Recovery layout | Primary image | Extra arguments |
|---|---|---|
| Dedicated recovery partition | `recovery.img` | none in the normal case |
| Recovery stored in boot | `boot.img` | usually auto-detected; use `--recovery-layout boot` only when verified |
| Recovery resources in vendor_boot | `vendor_boot.img` or a split-set primary | add companion images when available |
| Android 13+ split GKI | `init_boot.img` | normally add `--boot-image` and `--vendor-boot` |

Do not guess a recovery layout only to make generation continue. NEXT rejects
ambiguous vendor ramdisks instead of silently selecting a board-specific
fragment that may belong to a different target.

## Common examples

### Dedicated recovery.img

Linux/Colab:

~~~bash
./launcher.sh recovery.img -o output
~~~

Windows:

~~~bat
launcher.cmd "C:\firmware\recovery.img" -o "C:\twrp-output"
~~~

### Recovery-as-boot

When auto detection is sufficient:

~~~bash
./launcher.sh boot.img -o output
~~~

When the layout has been independently verified as recovery-as-boot:

~~~bash
./launcher.sh boot.img --recovery-layout boot -o output
~~~

Windows uses the same options:

~~~bat
launcher.cmd "C:\firmware\boot.img" --recovery-layout boot -o "C:\twrp-output"
~~~

### Modern split GKI layout

Linux/Colab:

~~~bash
./launcher.sh init_boot.img \
  --boot-image boot.img \
  --vendor-boot vendor_boot.img \
  --skeleton twrp-14.1 \
  -o output
~~~

Windows Command Prompt:

~~~bat
launcher.cmd "C:\firmware\init_boot.img" ^
  --boot-image "C:\firmware\boot.img" ^
  --vendor-boot "C:\firmware\vendor_boot.img" ^
  --skeleton twrp-14.1 ^
  -o "C:\twrp-output"
~~~

PowerShell can place the command on one line, or use PowerShell's backtick for
line continuation.

### vendor_boot with multiple RECOVERY fragments

NEXT intentionally refuses to guess when `vendor_boot` contains more than one
typed RECOVERY ramdisk fragment.

Select a verified fragment by name:

~~~bash
./launcher.sh init_boot.img \
  --boot-image boot.img \
  --vendor-boot vendor_boot.img \
  --recovery-fragment recovery \
  -o output
~~~

Or by numeric vendor ramdisk table index:

~~~bash
./launcher.sh init_boot.img \
  --boot-image boot.img \
  --vendor-boot vendor_boot.img \
  --recovery-fragment 2 \
  -o output
~~~

The same `--recovery-fragment` option works through `launcher.cmd`.

### Extract image components only

This parses modern image structures without generating a TWRP device tree:

~~~bash
./launcher.sh init_boot.img \
  --boot-image boot.img \
  --vendor-boot vendor_boot.img \
  --extract-only extracted
~~~

Windows:

~~~bat
launcher.cmd "C:\firmware\init_boot.img" --boot-image "C:\firmware\boot.img" --vendor-boot "C:\firmware\vendor_boot.img" --extract-only "C:\extracted"
~~~

The extraction directory contains raw parsed components, expanded ramdisks and
`manifest.json`.

### Keep parsed components while generating

~~~bash
./launcher.sh init_boot.img \
  --boot-image boot.img \
  --vendor-boot vendor_boot.img \
  --extract-to parsed-images \
  -o output
~~~

### Replace an existing generated tree

NEXT refuses to overwrite an existing
`OUTPUT/<manufacturer>/<codename>/` tree by default.

Use `--overwrite` only when replacement is intentional:

~~~bash
./launcher.sh recovery.img -o output --overwrite
~~~

### Initialize the generated tree as a Git repository

~~~bash
./launcher.sh recovery.img -o output --git
~~~

This requires `git user.name` and `git user.email` to already be configured.
NEXT will not invent an identity.

## Recovery ramdisk output policy

NEXT extracts the selected recovery ramdisk and uses it as the source of truth,
but it does not blindly replace TWRP's own userspace by default.

Every generated device tree contains:

~~~text
recovery/
├── stock-root/
│   └── full selected stock recovery ramdisk
├── root/
│   └── conservative device-specific TWRP overlay
└── ramdisk-manifest.json
~~~

The default `auto` recovery-root policy resolves to the conservative
`minimal` overlay. This avoids copying a stock recovery binary, generic stock
`init`, `adbd`, or unrelated framework content over TWRP.

To request the conservative mode explicitly:

~~~bash
./launcher.sh recovery.img --recovery-root-mode minimal -o output
~~~

A complete stock overlay is available only as an explicit advanced override:

~~~bash
./launcher.sh recovery.img --recovery-root-mode full -o output
~~~

`full` can replace files that TWRP normally supplies itself. It should not be
treated as the default path.

## Skeleton profiles

`--skeleton` accepts:

| Value | Generated product prefix | Intended source generation |
|---|---|---|
| `auto` | selected from detected firmware SDK | recommended default |
| `omni` | `omni_<codename>` | legacy TWRP trees |
| `twrp-12.1` | `twrp_<codename>` | TWRP 12.1 |
| `twrp-14.1` | `twrp_<codename>` | TWRP 14.1 |

Example:

~~~bash
./launcher.sh recovery.img --skeleton twrp-14.1 -o output
~~~

## Partition metadata

NEXT does not invent partition sizes from compressed image file lengths.
Source image length minima are written only as BoardConfig comments and
into `generation-report.json`; they are not active build partition sizes.
Unambiguous stock fstab filesystem types are also recorded, with unknown
or conflicting types left unset. Stock patch metadata is accepted only if
it is a plausible date. Every generated tree still needs real boot testing.

Pass verified values from GPT/lpdump when they are required:

~~~bash
./launcher.sh recovery.img \
  --boot-size 67108864 \
  --recovery-size 104857600 \
  --super-size 9126805504 \
  --dynamic-group-size 9122611200 \
  -o output
~~~

These numbers are examples only, not recommended values for any device.

## Launcher-only commands

These commands are handled by the launcher itself instead of being passed to
the generator.

### Environment check

Linux/Colab:

~~~bash
./launcher.sh --doctor
~~~

Windows:

~~~bat
launcher.cmd --doctor
~~~

This checks the launcher's required environment and imports the Python
dependencies.

### Run the regression suite

Linux/Colab:

~~~bash
./launcher.sh --self-test
~~~

Windows:

~~~bat
launcher.cmd --self-test
~~~

This compiles the Python package and runs the repository unit tests.

### Set up without generating

Linux/Colab:

~~~bash
./launcher.sh --setup-only
~~~

Windows:

~~~bat
launcher.cmd --setup-only
~~~

This installs/checks dependencies and prints the ready-to-use examples.

### Run with no arguments

Local Windows and graphical Linux launchers open the GUI with no arguments.
Headless Linux enters terminal Easy Mode; Colab retains setup/usage output.

Google Colab and non-interactive Linux invocations keep the setup/usage output
behavior instead of waiting for local user input.

## What each launcher installs

### launcher.sh

On Debian/Ubuntu/Colab, the launcher:

1. verifies Python 3.8 or newer;
2. detects Colab when available;
3. installs missing host extraction utilities with `apt-get`;
4. installs the cloned package and Python dependencies with pip;
5. runs the normal NEXT CLI with the supplied arguments.

The modern parser itself handles supported CPIO compression in Python,
including Zstandard. Some system tools remain available for legacy fallback
paths.

### launcher.cmd

On Windows, the launcher:

1. looks for `python`, then `py -3`;
2. verifies Python 3.8 or newer;
3. checks the required Python modules;
4. installs the cloned package with pip only when dependencies are missing;
5. runs the normal NEXT CLI with the supplied arguments.

The modern parser does not require WSL for supported boot/recovery v3/v4,
`init_boot` v4, or `vendor_boot` v3/v4 images.

## Supported modern ramdisk compression

The native parser supports:

- raw newc CPIO;
- gzip;
- bzip2;
- XZ;
- LZMA;
- LZ4 frame;
- Android legacy LZ4;
- Zstandard.

Zstandard decoding is handled by the Python `zstandard` package; a separate
`zstd.exe` is not required on Windows.

## Windows notes

### Quote paths containing spaces

Use quotes around image and output paths:

~~~bat
launcher.cmd "C:\Users\Jay\My Firmware\recovery.img" -o "C:\TWRP Projects\output"
~~~

### CMD and PowerShell invocation

In Command Prompt:

~~~bat
launcher.cmd recovery.img -o output
~~~

In PowerShell:

~~~powershell
.\launcher.cmd recovery.img -o output
~~~

### Symlinks

Windows may restrict creation of symbolic links unless Developer Mode is
enabled or the process has sufficient privileges. NEXT rejects unsafe symlink
targets and Windows-style traversal attempts. If Windows cannot create a safe
symlink from the stock ramdisk, that host limitation can affect exact
filesystem reproduction.

### Legacy image fallback

Modern parsing is native Windows. Older image formats that fall back to the
legacy AIK toolchain may still need Linux or WSL.

## Colab notes

Colab stores uploaded/runtime files under `/content` by default.

Typical flow:

~~~bash
!git clone https://github.com/RectifyData/twrpdtgen-NEXT.git
%cd twrpdtgen-NEXT
!./launcher.sh /content/recovery.img -o /content/output
~~~

Colab runtimes are temporary. Copy generated output somewhere persistent before
ending the runtime if you need to keep it.

## Advanced environment controls

### Linux/Colab

`PYTHON_BIN`
: Override the Python command used by `launcher.sh`.

`TWRPDTGEN_SKIP_SYSTEM_DEPS=1`
: Skip the `apt-get` system dependency step.

`TWRPDTGEN_SKIP_PIP=1`
: Skip pip package installation.

Example:

~~~bash
PYTHON_BIN=python3.12 TWRPDTGEN_SKIP_SYSTEM_DEPS=1 ./launcher.sh --doctor
~~~

### Windows

`TWRPDTGEN_SKIP_PIP=1`
: Skip pip dependency installation.

This is intended for controlled development/CI environments where dependencies
are already installed.

## Troubleshooting

### "Python 3 was not found"

Install Python 3.8 or newer.

On Windows, make sure `python` is available on PATH or the Python Launcher
(`py`) is installed.

### "Specified primary image doesn't exist"

The first positional path does not point to a file. Check quoting and the
current working directory.

### "No stock fstab found in extracted ramdisks"

The selected input set does not expose a usable recovery fstab. Verify that the
correct recovery-bearing image and companion images were supplied.

### "Dedicated recovery was selected but no recovery.img ramdisk was supplied"

The chosen/detected layout is dedicated recovery, but the supplied image set
does not contain a parsed dedicated recovery ramdisk. Supply the correct
`recovery.img` or correct a manually forced layout.

### "Recovery-as-boot was selected but boot.img has no ramdisk"

The selected `boot.img` does not provide the recovery ramdisk expected for a
recovery-as-boot device. Verify the device layout and image set.

### "vendor_boot contains multiple RECOVERY fragments"

NEXT will not guess board-specific `board_id` semantics. Inspect the extracted
manifest and pass a verified fragment using `--recovery-fragment NAME` or
`--recovery-fragment INDEX`.

### Output tree already exists

NEXT does not overwrite an existing generated device tree automatically.

Use:

~~~bash
--overwrite
~~~

only when replacing that tree is intended.

### Windows pip installation fails

Run:

~~~bat
launcher.cmd --doctor
~~~

If the failure is inside pip, verify that the selected Python installation can
run:

~~~bat
python -m pip --version
~~~

or:

~~~bat
py -3 -m pip --version
~~~

### Need detailed Python errors

Pass `--debug` to the normal generator invocation:

~~~bash
./launcher.sh recovery.img --debug -o output
~~~

## Generated tree is not proof of bootability

The launcher only makes setup and invocation portable. A generated candidate
tree can still require device-specific work for:

- kernel compatibility;
- AVB policy;
- SELinux;
- FBE/metadata decryption;
- KeyMint/Gatekeeper;
- display/input quirks;
- firmware and kernel modules;
- OEM-specific wrappers;
- exact partition geometry.

Do not treat successful generation as proof that a recovery image built from
the tree is safe to flash.
