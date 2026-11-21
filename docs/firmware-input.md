# tdtnext — whole-firmware input

`twrpdtgen-NEXT` version **3.1.0a32** provides a Python console command:

```shell
python -m pip install .
tdtnext --help
tdtnext --input "C:\Firmware\AP_G975F.tar.md5" --output "C:\TWRP\output"
```

Python installers put `tdtnext` / `tdtnext.exe` on your activated Python environment's `Scripts`/`bin` PATH. When using a user installation, add that Scripts directory to PATH, or use the equivalent package entry point `python -m twrpdtgen --input ... --output ...`.

## Accepted firmware

- **Samsung:** single `AP_*.tar.md5` or `.tar`, optionally wrapped in the stock ZIP. Odin `.img.lz4` and `.img.ext4.lz4` are decompressed with Python `lz4`. A recognizable MD5 footer is verified. Supplying a combined firmware folder also works, provided there are no duplicate/conflicting partition images.
- **Motorola:** stock fastboot ZIP or extracted firmware directory, including `super.img_sparsechunk.0`, `.1`, etc. All numbered chunks must be present. Sparse chunks are reconstructed at their real block offsets rather than naively concatenated.
- **Google Pixel:** outer factory ZIP or inner `image-DEVICE-BUILD.zip`, including boot, vendor_boot, init_boot, dtbo, vendor and logical partition images. Nested archives are extracted with bounded streaming.
- **Generic:** raw `.img` files or directories containing known partition images; Android sparse ext4/EROFS partitions and dynamic super images are supported as inputs.

## Example

```shell
tdtnext --input "D:\factory-images\panther-factory.zip" --output "D:\twrp-next\out"
tdtnext --input "D:\firmware\AP_S918B.tar.md5" --output "D:\twrp-next\out"
tdtnext --input "D:\motorola\moto-stock.zip" --output "D:\twrp-next\out"
```

The output contains a generated `manufacturer/device/` tree and a `twrp-device-tree.zip` with `firmware-input-audit.json` and `fulltree-audit.json`. It preserves available firmware, VINTF, init metadata and kernel module sources from relevant partitions. Stock `recovery`, `init`, `adbd` and core system executables are **not** transplanted over TWRP.

## Automatic tools on Linux and Windows

Missing extraction tools install *only when needed*, with installer output and progress
visible. `tdtnext --setup-tools` pre-installs/verifies everything ahead of time.
`tdtnext --no-auto-install --input ... --output ...` disables dependency installation.

- `lpunpack` is first taken from PATH. Otherwise tdtnext installs the checksum-pinned
  Python `liblp==1.0.2` package into a user-scoped cache, without modifying system
  Python or requiring administrator access. It supports only the layout features of
  that implementation (not every split-super vendor layout).
- For ext4 extraction, tdtnext uses `debugfs` from `e2fsprogs`; for EROFS extraction
  it uses `fsck.erofs` from `erofs-utils`. Native tools on PATH are preferred.
- **Linux:** `apt-get`, `dnf`, `pacman`, `zypper`, and `apk` are recognized. Missing
  packages are installed through the distribution package manager; sudo prompts and
  progress are visible. Packages are not upgraded unless your package manager does so.
- **Windows:** bundled `install-windows.cmd` sets up Python (using visible `winget`
  if missing), an isolated Python virtualenv, user PATH, and calls `tdtnext
  --setup-tools`. When filesystem utilities aren't installed natively, it uses
  Microsoft's WSL/Ubuntu, installing WSL if absent and installing `e2fsprogs`
  / `erofs-utils` in Ubuntu using visible apt output and sudo prompts.
  WSL installation may require administrator approval, Ubuntu first-run setup,
  and a **manual** Windows restart. tdtnext never silently restarts the system.
- With Windows WSL extraction, path translation uses `wslpath` to access the source
  files from the default WSL distro. Its Linux default distro must support apt;
  for other distros, provision packages manually.

**Limits:** Firmware output is only a candidate source tree. This tool does not
flash, repack, sign or verify TWRP boot. A physical device build/boot and encrypted
storage validation remain essential. The installer uses the network on first install.
A user needs sufficient free disk space for extracted firmware images and files.

## Python API

```python
from pathlib import Path
from twrpdtgen.tdtnext import run_firmware_job

tree, zip_archive = run_firmware_job(
    Path("firmware/factory.zip"), Path("output")
)
```

Legacy single-image generation remains available via `python -m twrpdtgen recovery.img`.

Example: `tdtnext --input ~/Downloads/stock.zip --output ~/TWRPTrees` automatically installs lpunpack if a super partition requires it.
