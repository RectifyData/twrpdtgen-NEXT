# twrpdtgen-NEXT 3.1.0a37 — Foreground Colab output

Experimental source preview. No bootable recovery is included.

Both Colab notebooks now run setup and generation synchronously in a foreground pseudo-terminal, relay stdout and stderr as they arrive, show progress on long quiet stages, propagate nonzero exits and terminate the active process group when interrupted. Added visible messages for firmware download, extraction, verification, tree generation and packaging. The previous image-only and full firmware workflows remain available. Live Colab/FUS and actual recovery boot still require validation.

Full-firmware filesystem tools now relay stdout/stderr live while retaining diagnostic text and execution timeouts.
