# twrpdtgen-NEXT skeleton and safety preview

- Added modern `twrp-12.1` and `twrp-14.1` product skeleton profiles.
- Added explicit recovery-layout and partition-size options.
- Removed dangerous hardcoded super partition geometry, synthetic patch
  levels, blanket AVB-disabling flags, and upstream test-signing defaults.
- Fixed duplicate dynamic-partition enumeration and silent tree deletion.
- Added regression checks in CI and documented current GKI limitations.

**Experimental source generator release only.** No boot/recovery image is
included or asserted bootable. Review every generated device tree before use.
