# twrpdtgen-NEXT 3.1.0a26 — simpler UI, source-grounded tree metadata

Source-only prerelease (not a ready-to-flash recovery).

- PyQt5 now uses native Windows/Linux controls, lighter spacing, and concise
  Generate / Settings / Updates tabs. Removed hardcoded dark-card styling,
  unnecessary badges, and promotional descriptions.
- Simplified Android browser GUI and Tk fallback labels, spacing, and forms.
  The CLI, browser, Tk and Qt generators keep synchronized settings.
- Fixed an accuracy bug: stock image file lengths are **not** verified
  physical partition capacities. NEXT records aligned image lengths only as
  commented minima, not active BoardConfig partition size assignments.
  Explicit user-provided partition sizes remain active where supplied.
- Read ext4/F2FS/ERoFS types from unambiguous selected stock fstab entries
  instead of inventing ext4 defaults. Conflicting/missing types stay unset.
- Reject implausible patch dates, including 2099 placeholders.
- Generate `generation-report.json` with source provenance, size evidence,
  AVB caveats, and outstanding validation requirements.
- Added and updated automated tests for conservative template output,
  filesystem detection, security patch validation, and UI action labels.

To receive improved metadata, regenerate trees from original stock images.
Generating a tree is not proof of recovery bootability or safe flashing.
