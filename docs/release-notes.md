# twrpdtgen-NEXT 3.1.0a11 — Colab stale-code isolation

This prerelease fixes a Colab-only update hazard found by inspecting a newly
regenerated Galaxy A20s device-tree ZIP after 3.1.0a10.

The notebook had correctly pulled newer source files, but its long-lived Python
kernel could still hold older imported `twrpdtgen.cloud_tree` or
`twrpdtgen.cloud_slice` modules. That produced a mixed-generation artifact:
new BoardConfig templates were visible from disk while the old in-memory ZIP
packager still bundled stock-root, dereferenced symlinks, and omitted newly
generated files.

Fixes:

- Runs cloud slicing and full device-tree generation through fresh
  `python -m twrpdtgen...` subprocesses on every execution.
- Keeps Colab browser downloads in the notebook kernel after the subprocess
  succeeds, so detailed child-process diagnostics remain visible.
- Prints the exact twrpdtgen version and Git commit loaded after the setup/pull
  cell.
- Adds a notebook regression test that prevents reintroducing direct in-kernel
  imports of the cloud generator entry points.
- Generated README files now include the twrpdtgen-NEXT version, making mixed or
  stale artifacts easier to identify during inspection.

The inspected regenerated A20s tree did confirm that `minimal` recovery-root
mode was working: its build overlay was only about 2 KiB instead of the previous
~118 MiB full stock userspace. The remaining stale ZIP behavior was caused by
the notebook module cache, not the minimal-overlay generator.

**Experimental source generator prerelease.** Regenerate artifacts after
updating the notebook; device-specific build and boot validation is still
required before flashing.
