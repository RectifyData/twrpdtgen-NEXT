# twrpdtgen-NEXT 3.1.0a34 — Pixel/Android 17 vendor_boot recovery fix

**Experimental source preview.** No bootable recovery image is included.

The generator now distinguishes universal vendor_boot v4 PLATFORM/NONE/DLKM
fragments from OEM-specific board variants instead of aborting immediately
when no typed RECOVERY fragment exists. Conflicting common files are not
silently combined. Excluded board-specific fragments are recorded in the
generated metadata, and the import can fall back to generic init_boot plus an
extracted vendor/odm stock fstab with explicit warnings.

Reported with Google Pixel 11 Pro Fold (yogi), Android 17 QPR2 factory package
\`yogi_beta-cp41.260831.019-factory-d1d1450f.zip\`.

Regression coverage includes variant exclusion, conflict detection, fallback,
original typed-fragment selection, and stock partition fstab lookup. The real
firmware ZIP was not supplied in this session for a full end-to-end retest.
Device-specific boot, encryption, SELinux, and signing remain unverified.
