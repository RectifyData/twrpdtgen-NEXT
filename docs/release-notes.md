# twrpdtgen-NEXT 3.1.0a27 — use plain git pull for updates

Source-only prerelease. Not a flashable recovery image.

- The Git updater now invokes **plain git pull** on the checkout's
  configured tracking branch. It does not invoke git merge or git checkout,
  or force-reset or stash files.
- Update checking still fetches current upstream metadata and confirms a
  clean, behind-only checkout. An already-current, dirty, or diverged
  repository cannot start an update.
- A local pull.ff=false configuration that would force a merge commit is
  rejected to protect the working copy.
- PyQt5, Tk fallback and Android browser interfaces display a clear
  "Pull updates" action and "git pull" progress/confirmation wording.
- CLI and Git regression tests assert that exactly plain git pull is called
  and that no pull is invoked for an up-to-date checkout.
- All recovery generation accuracy improvements from a26 remain intact.

Install source code, not an APK or Windows executable. Physical recovery
bootability and flash safety remain unverified.
