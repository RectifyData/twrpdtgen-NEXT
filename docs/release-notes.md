# twrpdtgen-NEXT 3.1.0a4 — Google Colab launcher

This prerelease adds a root-level launcher designed for cloned Google Colab
sessions while remaining usable on normal Debian/Ubuntu Linux hosts.

- Adds `launcher.sh` for clone-and-run Colab setup.
- Detects Google Colab without requiring a separate notebook.
- Installs only missing Linux extraction tools instead of performing a full
  package reinstall on every launch.
- Installs the cloned repository in editable mode so the launcher always runs
  the checked-out NEXT source.
- Preserves the caller working directory, so relative input/output paths behave
  normally while the package itself is loaded from the clone.
- Passes all normal arguments directly to `python3 -m twrpdtgen`.
- Adds launcher-only `--doctor`, `--self-test`, and `--setup-only` modes.
- Adds Colab examples for dedicated recovery.img and split
  boot/init_boot/vendor_boot layouts.
- CI now validates launcher shell syntax and exercises the launcher self-test
  path with bootstrap installation disabled.

**Experimental source generator prerelease.** Colab setup and the parser/test
suite are validated in CI. Device-tree correctness still depends on the actual
stock images and target-specific recovery requirements.
