# twrpdtgen-NEXT 3.1.0a20 — desktop GUI + independent CLI

Source-only preview release.

- Full native Tk GUI: image, archive and folder pickers; optional
  boot/vendor_boot/init_boot companion files; TWRP profile and recovery layout
  controls; partition-size fields; ZIP export; extraction-only mode.
- Live stage messages, visible progress indicator, Open Output,
  floating Tools menu, and overwrite confirmation.
- Separate twrpdtgen-gui and twrpdtgen-cli commands.
- Windows/Linux desktop defaults to GUI; existing CLI and headless Colab
  workflows are retained. Windows launcher no longer references a missing label.
- Headless GUI-backend tests. Bootstrap installation output is visible.

Source-tree generation is not proof of bootability or flash safety. Verify
partition capacity, actual recovery placement, encryption, SELinux, AVB,
kernel and OEM packaging independently before flashing.
