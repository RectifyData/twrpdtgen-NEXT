# twrpdtgen-NEXT 3.1.0a5 — native Windows launcher

This prerelease adds a native Windows CMD entry point for the modern
boot/recovery parser while keeping the Linux/Colab launcher.

- Adds `launcher.cmd` with the same image-to-output syntax as launcher.sh.
- Detects `py -3` or `python`, validates Python 3.8+, and installs cloned
  repo dependencies only when they are missing.
- Runs directly from the checked-out source tree and preserves normal Windows
  absolute/relative paths.
- Supports native Windows handling for boot/recovery header v3/v4, init_boot v4
  and vendor_boot v3/v4.
- Replaces the external zstd CLI requirement with Python `zstandard`, removing
  one host-tool dependency from Windows/Colab/Linux modern parsing.
- Keeps legacy AIK-only formats explicitly separate; those may still need
  Linux/WSL host tooling.
- Adds Windows `--doctor`, `--self-test`, and `--setup-only` launcher
  modes.
- Adds a Windows GitHub Actions job that runs the CMD launcher doctor and full
  regression suite on `windows-latest`.
- Keeps Linux/Colab CI and release gating intact.

**Experimental source generator prerelease.** Native Windows launcher and modern
parser behavior are CI-tested, but device-tree correctness still depends on the
actual stock images and device-specific recovery requirements.
