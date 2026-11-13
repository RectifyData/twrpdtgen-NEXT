# twrpdtgen-NEXT 3.1.0a24 — Git updater + optional PyQt5 desktop GUI

Source-only prerelease.

- New native PyQt5 (Qt Widgets) desktop interface on Windows/Linux with a
  dark theme, floating Tools menu, file pickers, advanced options synced
  from the CLI parser, tree/ZIP export, extraction, and visible progress.
- Existing Tk desktop GUI remains a fallback; the CLI and Android localhost
  browser GUI remain supported. PyQt5 is an optional `qt` package extra.
- Git updater available from both desktop GUIs, the Android browser GUI,
  launchers, and the `twrpdtgen-update` CLI.
- Git check fetches configured upstream and shows ahead/behind/dirty status.
  Git apply requires explicit approval and refuses dirty working trees,
  untracked files, detached heads, and diverged/ahead local branches.
  Only fast-forward merges are allowed; no force-reset or stash.
- Added local-repository unit tests for clean fast-forward, dirty refusal,
  diverged refusal, offline checks, invalid installations, and web endpoints.
- Added optional headless/offscreen PyQt5 smoke tests and GUI/CLI parity
  checks in GitHub Actions.

No automatic flashing, silent installation, or background update. Updating
source code does not prove generated TWRP is bootable or flash-safe; verify
real partition capacity, kernel, AVB, SELinux and encryption independently.
