# Cloud-assisted Samsung firmware slicing

twrpdtgen-NEXT can use a cloud machine such as Google Colab as a bandwidth
middleman for official Samsung firmware.

Instead of downloading an 8–12+ GB firmware bundle to a local PC just to obtain
one small image, the full FUS download and decryption happen in the cloud. NEXT
then streams only the requested payload out of the nested Samsung package,
decompresses it remotely, and downloads only the final standalone image to the
local machine.

## Data flow

~~~text
Samsung FUS
    |
    | full encrypted firmware transfer
    v
Google Colab / cloud VM
    |
    | samloader-rs downloads + decrypts on the fly
    v
decrypted firmware ZIP
    |
    | stream only AP_/BL_/CP_/CSC_ *.tar.md5
    | no full TAR extraction
    v
requested payload (for example boot.img.lz4)
    |
    | remote LZ4 decode
    v
boot.img
    |
    | only this file crosses to the local computer
    v
Windows / local machine
~~~

The local machine still downloads the requested final payload, so the practical
goal is **zero local full-firmware bandwidth**, not literally zero bytes.

## Quickest path: Google Colab notebook

Open colab/cloud_firmware_slice.ipynb.

The notebook exposes form fields for model, region/CSC, partition, optional
exact firmware version, package override, and parallel download thread count.
The final cell triggers a Colab browser download for only the extracted payload.

Direct Colab link:

https://colab.research.google.com/github/RectifyData/twrpdtgen-NEXT/blob/master/colab/cloud_firmware_slice.ipynb

## Command-line use in Colab or Linux

~~~bash
git clone https://github.com/RectifyData/twrpdtgen-NEXT.git
cd twrpdtgen-NEXT
python3 -m pip install -e .
~~~

Fetch the latest firmware for a device and return only boot.img:

~~~bash
python3 -m twrpdtgen.cloud_slice fetch \
  -m SM-G975F \
  -r BTU \
  --partition boot \
  -o /content/boot.img \
  --colab-download
~~~

The same operation through the convenience launcher:

~~~bash
bash cloud-slice.sh fetch \
  -m SM-G975F \
  -r BTU \
  --partition boot \
  -o /content/boot.img \
  --colab-download
~~~

## Specific firmware version

~~~bash
python3 -m twrpdtgen.cloud_slice fetch \
  -m SM-S938B \
  -r EUX \
  -v 'S938BXXS5AYG4/S938BOXM5AYG4/S938BXXS5AYG4/S938BXXS5AYG4' \
  --partition boot \
  -o /content/boot.img \
  --colab-download
~~~

If the version option is omitted, samloader-rs requests the latest firmware
available for the supplied model and region.

## Supported target examples

Typical direct Odin-package payloads include boot.img, recovery.img,
init_boot.img, vendor_boot.img, dtbo.img, vbmeta.img, super.img, modem.bin,
and bootloader files. Compressed .lz4 variants are detected and decoded
remotely.

Both standard LZ4 frames and Samsung/Android legacy LZ4 streams are supported.
Legacy Odin payloads use magic `02 21 4c 18` and are decoded block-by-block
instead of being loaded wholly into memory.

You can pass either a short name such as boot or a filename such as boot.img.

## Package selection

Samsung firmware ZIPs usually contain AP_, BL_, CP_, CSC_, HOME_CSC_, and
sometimes USERDATA_ TAR.MD5 packages.

By default NEXT tries the likely package first: AP for normal Android images,
CP for modem payloads, BL for common bootloader payloads, and CSC for common
CSC/cache-style payloads. It falls back to the other packages if necessary.

Force a package when desired:

~~~bash
python3 -m twrpdtgen.cloud_slice fetch \
  -m SM-G975F \
  -r BTU \
  --partition modem \
  --package CP \
  -o /content/modem.bin \
  --colab-download
~~~

## Exact TAR member selection

For unusual firmware layouts, request an exact member:

~~~bash
python3 -m twrpdtgen.cloud_slice fetch \
  -m SM-G975F \
  -r BTU \
  --partition boot \
  --member boot.img.lz4 \
  --package AP \
  -o /content/boot.img
~~~

## Slice an already-downloaded firmware ZIP

~~~bash
python3 -m twrpdtgen.cloud_slice slice firmware.zip \
  --partition recovery \
  -o recovery.img
~~~

## Why the TAR package is streamed

NEXT does not extract the whole AP TAR.MD5 to disk. It opens the outer firmware
ZIP, opens the selected TAR member as a stream, walks TAR headers sequentially,
and copies only the target file. If the target ends in .lz4, it is decoded
directly into the final output file.

Cloud disk usage therefore mainly consists of the decrypted outer firmware ZIP
while the job is active plus the final requested payload. It does not require a
second multi-gigabyte unpacked AP directory.

## Full firmware cleanup

By default the cloud firmware ZIP is deleted after the payload is produced.

Keep it only when needed:

~~~bash
python3 -m twrpdtgen.cloud_slice fetch \
  -m SM-G975F \
  -r BTU \
  --partition boot \
  --work-dir /content/fw-work \
  --keep-firmware \
  -o /content/boot.img
~~~

When keep-firmware is used without work-dir, NEXT uses ./.twrpdtgen-cloud/ as
a persistent work directory.

## samloader-rs bootstrap

NEXT delegates Samsung FUS protocol handling and ENC2/ENC4 decryption to
topjohnwu/samloader-rs.

When samloader is not already on PATH, NEXT queries the latest GitHub release,
selects the matching prebuilt ZIP, downloads it into the NEXT cache, requires a
GitHub sha256 digest for that release asset, verifies the digest, and only then
extracts the executable.

If no digest is published, automatic installation is refused. A manually
verified executable can be supplied with --samloader.

The project does not embed Samsung FUS encryption keys or reimplement Samsung
firmware cryptography.

## Parallel cloud download

samloader-rs supports parallel FUS downloads. NEXT defaults to 8 connections.

~~~bash
python3 -m twrpdtgen.cloud_slice fetch \
  -m SM-G975F \
  -r BTU \
  --partition boot \
  -j 12 \
  -o /content/boot.img
~~~

## Output verification

After slicing, NEXT prints the source package, exact TAR payload member, final
output path, byte size, SHA-256, and whether LZ4 decoding was performed.

Existing final payloads are not overwritten by default. Pass --overwrite only
when replacement is intentional.

## What this saves

For a normal boot.img request:

- local bandwidth: only the final boot image instead of the full firmware;
- local disk: only the final payload;
- local CPU: no ENC4 decryption or multi-gigabyte TAR processing;
- cloud disk: the full firmware ZIP temporarily, but no full AP extraction;
- cloud CPU/network: FUS download, decryption, archive scan, and LZ4 decode.

## Limitations

This implementation extracts files that are direct members of Samsung Odin TAR
packages. Asking for super returns super.img. It does not yet run a second
lpunpack stage to extract system, vendor, product, or other logical partitions
from inside super.img.

FUS availability is controlled by Samsung. A firmware version no longer served
by Samsung cannot be recovered by NEXT itself.

A payload copied from official firmware is not automatically safe to flash on a
different model, bootloader revision, region, or partition layout.


## Galaxy A20s SM-A207F / NEE

This model/CSC pair was used to validate the failure path that motivated
3.1.0a8. Samsung FUS currently reports:

~~~text
A207FXXS5CWF1/A207FOXM5CWD1/A207FXXS5CWD1/A207FXXS5CWF1
~~~

Example:

~~~bash
python3 -m twrpdtgen.cloud_slice fetch \
  -m SM-A207F \
  -r NEE \
  --partition recovery \
  --package AP \
  -o /content/recovery.img \
  --colab-download
~~~

The Colab notebook now prints the actual cloud-slicer error directly if a later
download/archive/decompression step fails; it no longer replaces the useful
message with a generic `CalledProcessError`.
