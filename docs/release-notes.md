# twrpdtgen-NEXT 3.1.0a35 — Colab refresh

Experimental source preview. No bootable recovery image is included.

- Both notebooks now use the standalone launcher’s isolated environment and fresh subprocesses, with automatic missing host-tool setup.
- Generic notebook retains upload-and-run image discovery and adds full firmware ZIP/TAR/TAR.MD5 import, including the firmware audit.
- Samsung FUS notebook retains extraction and tree-generation modes, with current layout, root, fragment, package and thread options.
- Generated archives remain candidate source trees. Real firmware, hardware boot and a live Colab session need separate validation.
