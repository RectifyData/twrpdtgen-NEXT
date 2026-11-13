# twrpdtgen-NEXT 3.1.0a18 — source-image-based partition size hints

This source-only prerelease hardcodes provisional BoardConfig size limits
instead of leaving the dedicated recovery field blank.

- Infer boot, recovery and modern vendor_boot/init_boot size hints from their
  actual source file lengths, rounded up to 4 KiB.
- Mark all inferred values as PROVISIONAL, not verified partition capacity.
- Accept verified --boot-size / --recovery-size overrides; reject overrides
  smaller than the respective input source image.
- Keep recovery-as-boot separate from a dedicated recovery partition.
- Add generation and size-bound regression tests.

Flash safety, partition table geometry, build success, AVB, encryption,
SELinux and bootability remain unverified until device-specific validation.
