# twrpdtgen-NEXT 3.1.0a25 — cleaner Qt UI and Git updater correction

Source-only prerelease; retains desktop PyQt5, Tk fallback, Android/browser GUI,
and the independent CLI.

- Reorganized the desktop PyQt5 workspace into three focused tabs:
  Build tree, Advanced settings, and Updates.
- Refined the visual hierarchy, colors, section spacing, buttons and logs
  to make regular firmware extraction less cluttered.
- Added clear Git update state labels: not checked, up to date, local changes,
  branch ahead/diverged, and update available.
- Disabled the Git Update button and Tools action until a fresh check
  confirms a clean, behind-only upstream branch. This applies to PyQt5,
  Tk fallback, and localhost Android/browser GUI.
- A confirmed `twrpdtgen-update --apply` now rejects already-up-to-date
  checkouts rather than incorrectly reporting an update. No Git merge
  or checkout occurs when no new commits exist.
- Tests cover real local Git branches, no-op merge prevention, desktop
  disabled/enabled state transitions, and blocked localhost API updates.
- Source recovery trees remain unverified for real booting or flashing.

Installation is visible, Git updates are never silent, and no existing user
files are force-reset or stashed.
