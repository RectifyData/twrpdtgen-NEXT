# twrpdtgen-NEXT 3.1.0a6 — launcher documentation

This prerelease documents the cross-platform launcher workflow introduced in
the previous previews.

- Adds `docs/launchers.md` as the complete launcher reference.
- Documents Google Colab, Debian/Ubuntu Linux, Windows Command Prompt and
  Windows PowerShell.
- Defines the common image-to-output syntax for `launcher.sh` and
  `launcher.cmd`.
- Clarifies that `-o/--output` is an output parent directory and that the
  generated tree is placed under `<output>/<manufacturer>/<codename>/`.
- Adds examples for dedicated recovery, recovery-as-boot, split GKI layouts,
  vendor_boot RECOVERY fragment selection, extract-only and component export.
- Documents recovery-root policies, skeleton profiles, verified partition-size
  overrides, overwrite behavior and generated Git repositories.
- Documents launcher-only `--doctor`, `--self-test`, and `--setup-only`
  commands.
- Documents native Windows compression support, path quoting, symlink behavior,
  legacy AIK/WSL limitations and Colab runtime persistence.
- Adds troubleshooting for missing Python/images/fstab, ambiguous vendor_boot
  fragments, existing output trees and pip failures.
- Links the full guide from both the Windows and Colab sections of the README.

**Experimental source generator prerelease.** Documentation and launchers are
validated against the current CLI and CI-tested launcher behavior. A generated
candidate tree is not proof that a recovery image is safe to flash.
