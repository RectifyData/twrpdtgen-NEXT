# twrpdtgen-NEXT 3.1.0a22 — mobile/browser GUI reliability update

Source-only prerelease with the desktop Tk GUI, mobile localhost GUI,
and fully independent CLI.

- Termux launcher opens the browser GUI before invoking Linux-only tooling
  checks or testing for an attached TTY.
- Optional .img.lz4 companion images are decoded in isolated temporary
  staging folders using the same validated decoder as primary images.
- Unsupported companion formats and conflicting image roles are rejected.
- New regression test verifies decoded companion image handoff.
- Prior mobile file picker/upload/ZIP download and desktop GUI continue.

A generated recovery source tree is not confirmed flash-safe or bootable.
