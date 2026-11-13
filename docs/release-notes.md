# twrpdtgen-NEXT 3.1.0a23 — synchronized CLI and both GUIs

Source-only prerelease. One argparse option definition and a shared generator
execution backend now power the CLI, desktop GUI and Android/Termux browser GUI.

- Derives CLI argument names, choices, defaults, types, and descriptions from
  the single `twrpdtgen.main.build_parser()` function.
- Desktop GUI renders additional CLI flags automatically and populates its
  existing recovery-layout/profile dropdowns from the parser.
- Android/browser GUI renders the same controls from local `GET /api/options`
  and keeps its existing mobile-friendly layout.
- Both GUIs parse their settings with the actual CLI parser, then call
  `execute_cli_job` (the same backend used by the command-line program).
- Keeps ZIP outputs uniquely named, supports init_boot and companion images,
  and preserves tree + ZIP and component-extraction modes.
- Adds tests to simulate future CLI arguments, validate pass-through and
  web schema consistency, and reject unsupported option shapes.

New supported CLI arguments appear automatically in both GUIs. Complex
future arguments require an adapter; CI fails loudly instead of omitting them.
These programs generate candidate sources and do not prove recovery bootability,
AVB correctness, encryption, partition capacity, or flash safety.
