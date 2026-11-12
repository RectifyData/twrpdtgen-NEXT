# twrpdtgen-NEXT

A safety-oriented evolution of [twrpdtgen](https://github.com/twrpdtgen/twrpdtgen)
for generating **candidate TWRP device-tree skeletons** from stock
`recovery.img` and compatible `boot.img` ramdisks.

NEXT adds version-selectable product skeletons, defensive output handling,
safer metadata generation, and a validation baseline. **A generated tree is
not a working recovery until compiled and tested on the actual device.**

## Skeletons

| Mode | Product | Recovery common config | Suggested source |
|---|---|---|---|
| `omni` | `omni_<codename>` | `vendor/omni/config/common.mk` | Legacy Omni-based TWRP |
| `twrp-12.1` | `twrp_<codename>` | `vendor/twrp/config/common.mk` | TWRP 12.1 |
| `twrp-14.1` | `twrp_<codename>` | `vendor/twrp/config/common.mk` | TWRP 14.1 |
| `auto` | Based on stock API | Based on stock API | SDK >=34: 14.1, SDK 31–33: 12.1, otherwise legacy |

Auto mode only reads Android API data from stock ramdisk properties; it does
not infer the running host's Android version. If the API cannot be read,
auto selects legacy. Override with `--skeleton` if you verified the device.

## Installation

Requires Python >=3.8, `cpio` on Linux, and the dependencies in
`pyproject.toml`.

```bash
python3 -m pip install .
python3 -m twrpdtgen recovery.img --skeleton twrp-14.1
```

For a verified A/B layout with recovery inside boot:

```bash
python3 -m twrpdtgen boot.img \
  --skeleton twrp-12.1 --recovery-layout boot \
  --boot-size 67108864
```

For a device with dynamic partitions and **confirmed** sizes from GPT and
`lpdump` (example values are illustrative, not device measurements):

```bash
python3 -m twrpdtgen recovery.img --skeleton twrp-14.1 \
  --super-size 9126805504 --dynamic-group-size 9122611200
```

Sizes are **byte counts**, aligned to 4096 bytes. Missing sizes produce
TODO comments, never invented dimensions. Output is
`output/<manufacturer>/<codename>/`. Existing trees are preserved unless
`--overwrite` is given. `--git` uses your configured Git identity.

## Source-image compatibility

The upstream project documents validation through Android 12. NEXT's
modern TWRP **product skeletons** do not imply that the original
`sebaubuntu-libs`/AIK image unpacker supports every Android 13–16 boot
header, standalone `vendor_boot`, `init_boot`, vendor ramdisk fragment,
or GKI layout. When extraction cannot find a ramdisk, the generator fails
rather than producing a falsely complete recovery tree.

### Still requiring device-specific implementation

- `vendor_boot` v3/v4 table parsing, fragment extraction and `init_boot`
  integration
- Reliable `super.img` metadata ingestion and retrofit dynamic layouts
- FBE decryption, KeyMint/Gatekeeper services, and stock SELinux integration
- Recovery build/test validation against a real TWRP checkout and hardware

## Developer checks

```bash
python3 -m compileall -q twrpdtgen tests
python3 -m unittest discover -s tests -v
```

Release artifacts are source-only; **no automatically generated device
image is certified safe to flash**.
