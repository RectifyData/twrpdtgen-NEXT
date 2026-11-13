# twrpdtgen-NEXT 3.1.0a21 — Android-friendly private browser GUI

Source-only prerelease. Adds a mobile browser interface to complement the
desktop Tk GUI and independent command-line program.

- New `twrpdtgen-web` and `python -m twrpdtgen.webgui` entry points.
- Local-only HTTP server bound to 127.0.0.1; intended for Android/Termux,
  Windows, and Linux browsers, without requiring a desktop/X11 environment.
- Mobile responsive dark interface with a floating Tools menu, Android file
  uploads and manual file paths, companion images, partition and recovery
  settings, output ZIP download and extraction-only mode.
- Per-session CSRF token, strict loopback Host checks, no cross-origin API,
  upload length/path validation, no third-party uploads or telemetry.
- Reuses the desktop GUI core and CLI generator; preserves generated tree
  integrity policies and does not flash devices.
- CLI/bootstrap docs and tests for localhost isolation, upload handling,
  token checks, generation responses, and downloaded ZIPs.
- Termux is detected by the Linux launcher to avoid incompatible apt bootstrapping.

Tested automation is not physical-device proof of recovery bootability.
Generated image file length is not verified partition capacity. User must
independently verify placement, AVB, encryption, and kernel compatibility.
