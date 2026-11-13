# SPDX-License-Identifier: Apache-2.0
"""Desktop GUI for twrpdtgen-NEXT; CLI continues to work independently.

Tk is imported only when a GUI is actually launched, so CLI, Termux,
Colab, and headless CI do not require an X server or tkinter.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse
import os
import queue
import subprocess
import sys
import threading
from typing import Callable, Optional

from twrpdtgen import __version__


@dataclass(frozen=True)
class GUIJob:
    source: Path
    output: Path
    mode: str = "tree"
    archive: Optional[Path] = None
    boot_image: Optional[Path] = None
    vendor_boot: Optional[Path] = None
    init_boot: Optional[Path] = None
    skeleton: str = "auto"
    recovery_layout: str = "auto"
    recovery_root_mode: str = "auto"
    recovery_fragment: Optional[str] = None
    boot_size: Optional[int] = None
    recovery_size: Optional[int] = None
    super_size: Optional[int] = None
    dynamic_group_size: Optional[int] = None
    include_stock_root: bool = False
    overwrite: bool = False
    cli_options: tuple = ()

    def validate(self):
        from twrpdtgen.next_support import NextOptions
        from twrpdtgen.option_sync import validate_extra_values

        extras = validate_extra_values(dict(self.cli_options))
        if self.mode == "extract" and (
                extras.get("git") or extras.get("extract_to")):
            raise ValueError(
                "Git commit and extra component export require tree mode")

        if self.mode not in ("tree", "extract"):
            raise ValueError("Choose Generate tree or Extract components")
        if not self.source.exists():
            raise FileNotFoundError("Input does not exist: {}".format(self.source))
        if not (self.source.is_file() or self.source.is_dir()):
            raise ValueError("Input must be a file or folder")
        if self.output.exists() and not self.output.is_dir():
            raise ValueError("Output location is not a directory")
        if self.archive is not None and self.archive.exists() and self.archive.is_dir():
            raise ValueError("ZIP output path must be a file, not a folder")
        for name in ("boot_image", "vendor_boot", "init_boot"):
            path = getattr(self, name)
            if path is not None and not path.is_file():
                raise FileNotFoundError(
                    "{} is not an existing image file: {}".format(name, path))
            if path is not None and not path.name.lower().endswith((".img", ".img.lz4")):
                raise ValueError(
                    "{} must be an .img or .img.lz4 file".format(name))
        if self.recovery_fragment and self.recovery_layout == "init_boot":
            raise ValueError(
                "A vendor_boot fragment cannot be selected with init_boot-only layout")
        NextOptions(
            skeleton=self.skeleton,
            recovery_layout=self.recovery_layout,
            recovery_root_mode=self.recovery_root_mode,
            boot_size=self.boot_size,
            recovery_size=self.recovery_size,
            super_size=self.super_size,
            dynamic_group_size=self.dynamic_group_size,
            overwrite=self.overwrite,
        )


@dataclass(frozen=True)
class GUIResult:
    tree: Optional[Path] = None
    archive: Optional[Path] = None
    extracted: Optional[Path] = None


def _optional_image(value: str) -> Optional[Path]:
    return Path(value.strip()).expanduser() if value.strip() else None


def parse_job(values: dict) -> GUIJob:
    """Convert form text to a validated job; shared by GUI and tests."""
    from twrpdtgen.next_support import parse_partition_size
    from twrpdtgen.option_sync import validate_extra_values

    extras = validate_extra_values(values.get("cli_options", {}))

    def size(name):
        raw = values.get(name, "").strip()
        return parse_partition_size(raw) if raw else None

    source = values.get("source", "").strip()
    if not source:
        raise ValueError("Choose a source image, archive, or folder first")
    output = values.get("output", "").strip()
    if not output:
        raise ValueError("Choose a destination folder")
    job = GUIJob(
        source=Path(source).expanduser(),
        output=Path(output).expanduser(),
        mode=values.get("mode", "tree"),
        archive=_optional_image(values.get("archive", "")),
        boot_image=_optional_image(values.get("boot_image", "")),
        vendor_boot=_optional_image(values.get("vendor_boot", "")),
        init_boot=_optional_image(values.get("init_boot", "")),
        skeleton=values.get("skeleton", "auto"),
        recovery_layout=values.get("recovery_layout", "auto"),
        recovery_root_mode=values.get("recovery_root_mode", "auto"),
        recovery_fragment=values.get("recovery_fragment", "").strip() or None,
        boot_size=size("boot_size"),
        recovery_size=size("recovery_size"),
        super_size=size("super_size"),
        dynamic_group_size=size("dynamic_group_size"),
        include_stock_root=bool(values.get("include_stock_root")),
        overwrite=bool(values.get("overwrite")),
        cli_options=tuple(extras.items()),
    )
    job.validate()
    return job


def _selection(source: Path):
    """Stage accepted input using Easy Mode; keep the chosen image primary."""
    from twrpdtgen.easy import prepared_input
    return prepared_input(source)


def run_job(job: GUIJob, report: Callable[[str], None] = print) -> GUIResult:
    """Run the shared CLI execution engine with GUI input preparation.

    All CLI options are parsed by main.build_parser, and passed to the same
    execute_cli_job backend used by the actual command-line application.
    """
    from twrpdtgen.auto_tree import discover_images
    from twrpdtgen.easy import _unique_path, _explicit_role, _extract_payload_stream
    from twrpdtgen.main import build_parser, execute_cli_job
    from twrpdtgen.option_sync import extra_cli_argv
    from twrpdtgen.tree_archive import archive_tree

    job.validate()
    report("Preparing selected image(s)...")
    with ExitStack() as resources:
        input_dir, explicit = resources.enter_context(_selection(job.source))
        try:
            discovered = discover_images(input_dir)
        except ValueError:
            if explicit is None:
                raise
            discovered = None

        primary = explicit or discovered.primary
        companions = {}
        for kind, manually_selected in (
                ("boot", job.boot_image),
                ("vendor_boot", job.vendor_boot),
                ("init_boot", job.init_boot)):
            automatic = getattr(discovered, kind, None) if discovered else None
            candidate = manually_selected or automatic
            if candidate is not None and (
                    candidate.resolve() == primary.resolve()
                    or candidate.resolve() == job.source.resolve()):
                candidate = None
            if (
                    candidate is not None and manually_selected is not None
                    and _explicit_role(primary) == kind):
                raise ValueError(
                    "The primary image and selected {} companion conflict".format(kind))
            if candidate is not None and candidate.name.lower().endswith(".img.lz4"):
                stage = Path(resources.enter_context(
                    TemporaryDirectory(prefix="twrpdtgen-companion-")))
                with candidate.open("rb") as stream:
                    candidate = _extract_payload_stream(
                        stream, candidate.name, stage)
            companions[kind] = candidate

        report("Primary image: {}".format(primary.name))
        for kind, path in companions.items():
            if path:
                report("Companion {}: {}".format(kind, path.name))

        # This argument vector is the same kind users can pass in terminal.
        # No GUI-only reimplementation of the generator's option handling.
        argv = [
            str(primary), "--output", str(job.output),
            "--skeleton", job.skeleton,
            "--recovery-layout", job.recovery_layout,
            "--recovery-root-mode", job.recovery_root_mode,
        ]
        for kind, flag in (
                ("boot", "--boot-image"),
                ("vendor_boot", "--vendor-boot"),
                ("init_boot", "--init-boot")):
            if companions[kind] is not None:
                argv.extend([flag, str(companions[kind])])
        if job.recovery_fragment:
            argv.extend(["--recovery-fragment", job.recovery_fragment])
        for kind, flag in (
                ("boot_size", "--boot-size"),
                ("recovery_size", "--recovery-size"),
                ("super_size", "--super-size"),
                ("dynamic_group_size", "--dynamic-group-size")):
            value = getattr(job, kind)
            if value is not None:
                argv.extend([flag, str(value)])
        if job.overwrite:
            argv.append("--overwrite")
        if job.mode == "extract":
            destination = _unique_path(job.output / "extracted-images")
            argv.extend(["--extract-only", str(destination)])
        argv.extend(extra_cli_argv(dict(job.cli_options)))
        parser = build_parser()
        try:
            args = parser.parse_args(argv)
        except SystemExit as exc:
            raise ValueError("Invalid generator settings") from exc

        job.output.mkdir(parents=True, exist_ok=True)
        report(
            "Extracting modern image components..." if job.mode == "extract"
            else "Parsing recovery and generating candidate TWRP tree...")
        result = execute_cli_job(args, direct=True)
        if job.mode == "extract":
            if result.extracted is None:
                raise RuntimeError("CLI backend returned no extracted components")
            report("Components saved to {}".format(result.extracted))
            return GUIResult(extracted=result.extracted)

        tree = result.tree
        if tree is None:
            raise RuntimeError("CLI backend returned no generated device tree")
        report("Creating portable ZIP (ZIP64 and symlinks supported)...")
        archive = job.archive or job.output / "twrp-device-tree.zip"
        if archive.suffix.lower() != ".zip":
            archive = archive.with_suffix(".zip")
        # Never silently erase an existing ZIP, even when replacing a tree.
        archive = _unique_path(archive)
        bundle = archive_tree(
            tree, archive, include_stock_root=job.include_stock_root)
        report("Tree: {}".format(tree))
        report("ZIP: {}".format(bundle))
        report("Generated source is NOT verified bootable or safe to flash.")
        return GUIResult(tree=tree, archive=bundle, extracted=result.extracted)


def can_launch_gui() -> bool:
    """Cheap availability check that does not create a window."""
    if sys.platform != "win32" and not (
            os.environ.get("DISPLAY")
            or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        import tkinter
    except ImportError:
        return False
    return True


def open_folder(path: Path) -> None:
    path = Path(path)
    if path.is_file():
        path = path.parent
    if not path.is_dir():
        raise FileNotFoundError(path)
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class NextWindow:
    """Scrollable Tk/ttk window with a floating Tools menu and live logs."""

    def __init__(self, root, initial_source=None, initial_output=None):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.result = None
        self.last_git_status = None
        root.title("twrpdtgen NEXT {}".format(__version__))
        root.geometry("900x740")
        root.minsize(650, 560)
        root.protocol("WM_DELETE_WINDOW", self._close)

        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Header.TLabel", font=("Arial", 13, "bold"))
        style.configure("Action.TButton", padding=(10, 5))
        style.configure("Section.TLabelframe", padding=(8, 6))

        from twrpdtgen.option_sync import interface_schema
        self.cli_schema = interface_schema()
        self.cli_extra_fields = {}
        self.fields = {}
        self.flags = {
            "overwrite": tk.BooleanVar(value=False),
            "include_stock_root": tk.BooleanVar(value=False),
        }
        start_dir = str(Path.home() / "TWRP-Trees")
        defaults = {
            "source": str(initial_source or ""),
            "output": str(initial_output or start_dir),
            "archive": "",
            "mode": "tree",
            "boot_image": "",
            "vendor_boot": "",
            "init_boot": "",
            "skeleton": self.cli_schema["choices"]["skeleton"]["default"],
            "recovery_layout": self.cli_schema["choices"]["recovery_layout"]["default"],
            "recovery_root_mode": self.cli_schema["choices"]["recovery_root_mode"]["default"],
            "recovery_fragment": "",
            "boot_size": "",
            "recovery_size": "",
            "super_size": "",
            "dynamic_group_size": "",
        }
        for name, value in defaults.items():
            self.fields[name] = tk.StringVar(value=value)

        header = ttk.Frame(root, padding=(15, 12))
        header.pack(fill="x")
        ttk.Label(
            header, text="twrpdtgen NEXT", style="Header.TLabel"
        ).pack(side="left")
        self.tools_button = ttk.Menubutton(header, text="Tools")
        self.tools_button.pack(side="right")
        menu = tk.Menu(self.tools_button, tearoff=False)
        menu.add_command(label="Open output folder", command=self._open_output)
        menu.add_command(label="Copy logs", command=self._copy_logs)
        menu.add_separator()
        menu.add_command(label="Check Git updates", command=self._check_updates)
        menu.add_command(
            label="Update from Git…", command=self._apply_update,
            state="disabled")
        self.tools_menu = menu
        menu.add_separator()
        menu.add_command(label="About and safety", command=self._about)
        self.tools_button["menu"] = menu

        # The editor scrolls independently from the log panel, so it remains
        # usable on smaller desktop displays and external phone screens.
        body_wrap = ttk.Frame(root, padding=(12, 0))
        body_wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(body_wrap, highlightthickness=0)
        scroll = ttk.Scrollbar(body_wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = ttk.Frame(canvas)
        anchor = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda event: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(
            anchor, width=event.width))
        canvas.bind("<Enter>", lambda event: canvas.bind_all(
            "<MouseWheel>", lambda e: canvas.yview_scroll(
                int(-e.delta / 120), "units")))
        canvas.bind("<Leave>", lambda event: canvas.unbind_all("<MouseWheel>"))

        source = ttk.LabelFrame(body, text="Source", style="Section.TLabelframe")
        source.pack(fill="x", padx=4, pady=(4, 8))
        self._path_row(source, "source", "Image / archive / folder",
                       pick="source")
        ttk.Label(
            source,
            text="Choose .img, .img.lz4, ZIP, TAR/TAR.MD5 or a folder. Matching companions are auto-detected.",
            wraplength=760,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 6))

        extra = ttk.LabelFrame(body, text="Additional images", style="Section.TLabelframe")
        extra.pack(fill="x", padx=4, pady=8)
        for role, label in (
                ("boot_image", "boot.img"),
                ("vendor_boot", "vendor_boot.img"),
                ("init_boot", "init_boot.img")):
            self._path_row(extra, role, label, pick="file")

        output = ttk.LabelFrame(body, text="Output", style="Section.TLabelframe")
        output.pack(fill="x", padx=4, pady=8)
        self._path_row(output, "output", "Destination directory", pick="folder")
        self._path_row(output, "archive", "ZIP path (optional)", pick="save")
        ttk.Label(output, text="A unique ZIP filename is chosen automatically to protect existing files.").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(1, 5))
        mode_row = ttk.Frame(output)
        mode_row.grid(row=3, column=0, columnspan=4, sticky="w")
        ttk.Radiobutton(
            mode_row, text="Generate TWRP tree + ZIP", variable=self.fields["mode"],
            value="tree").pack(side="left", padx=(0, 16))
        ttk.Radiobutton(
            mode_row, text="Extract parsed image components only",
            variable=self.fields["mode"], value="extract").pack(side="left")

        advanced = ttk.LabelFrame(body, text="Recovery", style="Section.TLabelframe")
        advanced.pack(fill="x", padx=4, pady=8)
        for row, (key, label) in enumerate((
                ("skeleton", "TWRP profile"),
                ("recovery_layout", "Recovery source"),
                ("recovery_root_mode", "Ramdisk overlay"))):
            ttk.Label(advanced, text=label, width=23).grid(
                row=row, column=0, sticky="w", pady=4)
            ttk.Combobox(
                advanced, state="readonly", width=26,
                textvariable=self.fields[key],
                values=self.cli_schema["choices"][key]["choices"]
            ).grid(row=row, column=1, sticky="w", pady=4)
        ttk.Label(advanced, text="Vendor recovery fragment").grid(
            row=3, column=0, sticky="w")
        ttk.Entry(
            advanced, textvariable=self.fields["recovery_fragment"], width=29
        ).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(
            advanced, text="Only choose a vendor fragment if you verified its identity.",
            wraplength=530).grid(row=4, column=0, columnspan=3, sticky="w")

        geometry = ttk.LabelFrame(body, text="Partition sizes", style="Section.TLabelframe")
        geometry.pack(fill="x", padx=4, pady=8)
        for row, (name, label) in enumerate((
                ("boot_size", "Boot"), ("recovery_size", "Recovery"),
                ("super_size", "Super"), ("dynamic_group_size", "Dynamic group"))):
            col = row % 2
            rr = row // 2
            ttk.Label(geometry, text=label, width=16).grid(
                row=rr, column=col * 2, sticky="w", padx=(4, 0), pady=4)
            ttk.Entry(
                geometry, textvariable=self.fields[name], width=16
            ).grid(row=rr, column=col * 2 + 1, sticky="w", padx=4, pady=4)
        ttk.Label(
            geometry, text="Leave unknown sizes blank. Image lengths are not partition capacities.",
            wraplength=760).grid(row=2, column=0, columnspan=4, sticky="w")

        synced = ttk.LabelFrame(
            body, text="Other options",
            style="Section.TLabelframe")
        synced.pack(fill="x", padx=4, pady=8)
        if not self.cli_schema["extras"]:
            ttk.Label(synced, text="All current CLI settings are covered above.").pack(
                anchor="w")
        for opt in self.cli_schema["extras"]:
            name = opt["name"]
            if opt["kind"] == "boolean":
                value = tk.BooleanVar(value=opt["default"])
                ttk.Checkbutton(
                    synced, text=opt["flag"] + "  —  " + opt["label"],
                    variable=value).pack(fill="x", anchor="w", pady=3)
            else:
                row = ttk.Frame(synced)
                row.pack(fill="x", pady=3)
                ttk.Label(
                    row, text=opt["flag"], width=23).pack(side="left")
                value = tk.StringVar(value=opt["default"])
                if opt["kind"] == "choice":
                    widget = ttk.Combobox(
                        row, textvariable=value, state="readonly",
                        values=opt["choices"])
                else:
                    widget = ttk.Entry(row, textvariable=value)
                widget.pack(side="left", fill="x", expand=True)
                ttk.Label(
                    synced, text=opt["label"], wraplength=650
                ).pack(fill="x", anchor="w")
            self.cli_extra_fields[name] = value

        checks = ttk.Frame(body)
        checks.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Checkbutton(
            checks, text="Replace an existing device tree (requires confirmation)",
            variable=self.flags["overwrite"]).pack(anchor="w")
        ttk.Checkbutton(
            checks, text="Include stock-root in ZIP (larger archive)",
            variable=self.flags["include_stock_root"]).pack(anchor="w")
        ttk.Label(
            checks, text="Generated source is not boot-tested.",
            wraplength=760).pack(anchor="w", pady=(6, 0))

        updater = ttk.LabelFrame(
            body, text="Updates",
            style="Section.TLabelframe")
        updater.pack(fill="x", padx=4, pady=8)
        update_row = ttk.Frame(updater)
        update_row.pack(fill="x")
        self.update_check_button = ttk.Button(
            update_row, text="Check for updates", command=self._check_updates)
        self.update_check_button.pack(side="left")
        self.update_apply_button = ttk.Button(
            update_row, text="Update from Git…", command=self._apply_update,
            state="disabled")
        self.update_apply_button.pack(side="left", padx=10)
        self.git_status_text = tk.StringVar(
            value="Not checked · Run Check for updates first")
        ttk.Label(updater, textvariable=self.git_status_text,
                  wraplength=740).pack(anchor="w", pady=(8, 0))
        ttk.Label(updater, text=(
            "Checks the configured upstream; refuses modified files or "
            "diverged branches. An update requires confirmation and restart."
        ), wraplength=740).pack(anchor="w", pady=(7, 0))

        footer = ttk.Frame(root, padding=(14, 7))
        footer.pack(fill="x", side="bottom")
        actions = ttk.Frame(footer)
        actions.pack(fill="x")
        self.go = ttk.Button(
            actions, text="Generate / Extract", style="Action.TButton",
            command=self._start)
        self.go.pack(side="left")
        ttk.Button(
            actions, text="Open output", command=self._open_output
        ).pack(side="left", padx=10)
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.pack(side="right", fill="x", expand=True, padx=(20, 0))
        self.status = tk.StringVar(value="Ready")
        ttk.Label(footer, textvariable=self.status).pack(fill="x", pady=(5, 4))
        self.log = ScrolledText(
            footer, height=7, wrap="word", font=("Consolas", 9),
            state="disabled")
        self.log.pack(fill="both")
        self._message("Select a source image to begin.")

    def _path_row(self, parent, name, label, pick):
        row = int(parent.grid_size()[1])
        parent.grid_columnconfigure(1, weight=1)
        self.ttk.Label(parent, text=label, width=23).grid(
            row=row, column=0, sticky="w", padx=(1, 6), pady=3)
        self.ttk.Entry(parent, textvariable=self.fields[name]).grid(
            row=row, column=1, sticky="ew", padx=4, pady=3)
        if pick == "source":
            self.ttk.Button(
                parent, text="File…", command=lambda: self._pick_file(name)
            ).grid(row=row, column=2, padx=3)
            self.ttk.Button(
                parent, text="Folder…", command=lambda: self._pick_dir(name)
            ).grid(row=row, column=3, padx=3)
        else:
            self.ttk.Button(
                parent, text="Browse…",
                command=lambda: (
                    self._pick_dir(name) if pick == "folder"
                    else self._pick_save(name) if pick == "save"
                    else self._pick_file(name))
            ).grid(row=row, column=2, padx=3)

    def _pick_file(self, name):
        from tkinter import filedialog
        value = filedialog.askopenfilename(
            parent=self.root,
            title="Select Android image / firmware" if name == "source"
            else "Select companion image")
        if value:
            self.fields[name].set(value)

    def _pick_dir(self, name):
        from tkinter import filedialog
        value = filedialog.askdirectory(
            parent=self.root, title="Choose directory", mustexist=True)
        if value:
            self.fields[name].set(value)

    def _pick_save(self, name):
        from tkinter import filedialog
        value = filedialog.asksaveasfilename(
            parent=self.root, title="Choose ZIP destination",
            defaultextension=".zip", filetypes=[("ZIP archive", "*.zip")])
        if value:
            self.fields[name].set(value)

    def _message(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", str(message).rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _copy_logs(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log.get("1.0", "end-1c"))

    def _open_output(self):
        from tkinter import messagebox
        try:
            selected = self.result.tree or self.result.extracted if self.result else None
            path = selected if selected else Path(self.fields["output"].get()).expanduser()
            open_folder(path)
        except Exception as exc:
            messagebox.showerror("Cannot open output", str(exc), parent=self.root)

    def _about(self):
        from tkinter import messagebox
        messagebox.showinfo(
            "About twrpdtgen-NEXT",
            "twrpdtgen-NEXT {}\n\nGUI and CLI share the same parser.\n"
            "TWRP trees are candidate source, not flashable images.\n"
            "Verify AVB, encryption, partition geometry and recovery "
            "boot behavior on the target device.".format(__version__),
            parent=self.root)

    def _form(self):
        result = {name: variable.get() for name, variable in self.fields.items()}
        result.update({name: bool(variable.get()) for name, variable in self.flags.items()})
        result["cli_options"] = {
            name: variable.get()
            for name, variable in self.cli_extra_fields.items()
        }
        return result

    def _sync_update_controls(self):
        allowed = (
            not self.busy and self.last_git_status is not None
            and self.last_git_status.can_apply)
        state = "normal" if allowed else "disabled"
        self.update_apply_button.configure(state=state)
        self.tools_menu.entryconfigure("Update from Git…", state=state)

    def _check_updates(self):
        self._start_update("check")

    def _apply_update(self):
        self._start_update("apply")

    def _start_update(self, mode):
        from tkinter import messagebox
        if self.busy:
            return
        if mode == "apply" and (
                self.last_git_status is None
                or not self.last_git_status.can_apply):
            self.status.set("No verified update available")
            self.git_status_text.set(
                self.last_git_status.explanation
                if self.last_git_status is not None
                else "Check for updates first; nothing was modified.")
            self._sync_update_controls()
            return
        if mode == "apply" and not messagebox.askyesno(
                "Confirm Git update",
                "Fetch and fast-forward the source checkout from its "
                "configured upstream?\n\nLocal edits and diverged "
                "commits will be protected. Restart after updating.",
                parent=self.root):
            return
        if mode == "check":
            self.last_git_status = None
            self.git_status_text.set("Checking remote tracking branch...")
        self.busy = True
        self.go.configure(state="disabled")
        self.update_check_button.configure(state="disabled")
        self._sync_update_controls()
        self.progress.start(14)
        self.status.set("Checking Git upstream..." if mode == "check"
                        else "Applying confirmed fast-forward...")
        worker = threading.Thread(
            target=self._update_worker, args=(mode,), daemon=True)
        worker.start()
        self.root.after(100, self._poll)

    def _update_worker(self, mode):
        try:
            from twrpdtgen.git_updater import check_updates, apply_update
            status = (
                check_updates() if mode == "check"
                else apply_update(confirmed=True))
            self.events.put(("update-check" if mode == "check"
                             else "update-done", status))
        except Exception as exc:
            self.events.put(("error", "{}: {}".format(type(exc).__name__, exc)))

    def _start(self):
        from tkinter import messagebox
        if self.busy:
            return
        try:
            job = parse_job(self._form())
        except Exception as exc:
            messagebox.showerror("Check the inputs", str(exc), parent=self.root)
            return
        if job.overwrite and not messagebox.askyesno(
                "Replace existing tree?",
                "The existing generated device tree could be deleted and "
                "recreated. Continue?", parent=self.root):
            return
        self.busy = True
        self.result = None
        self.go.configure(state="disabled")
        self.update_check_button.configure(state="disabled")
        self._sync_update_controls()
        self.progress.start(14)
        self.status.set("Working — see log below")
        self._message("")
        self._message("Starting {}...".format(job.mode))
        worker = threading.Thread(
            target=self._work, args=(job,), daemon=True)
        worker.start()
        self.root.after(100, self._poll)

    def _work(self, job):
        try:
            result = run_job(
                job, report=lambda message: self.events.put(("log", message)))
            self.events.put(("done", result))
        except Exception as exc:
            self.events.put(("error", "{}: {}".format(type(exc).__name__, exc)))

    def _poll(self):
        from tkinter import messagebox
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._message(value)
                    self.status.set(str(value))
                else:
                    self.busy = False
                    self.progress.stop()
                    self.go.configure(state="normal")
                    self.update_check_button.configure(state="normal")
                    if kind == "update-check":
                        self.last_git_status = value
                        self.git_status_text.set(value.explanation)
                        self._message(
                            "{} · Upstream {}: {} behind, {} ahead, dirty={}."
                            .format(value.state, value.upstream, value.behind,
                                    value.ahead, value.dirty))
                        self.status.set(
                            "Update available" if value.can_apply
                            else value.explanation)
                    elif kind == "update-done":
                        self.last_git_status = value
                        self.git_status_text.set(value.explanation)
                        self._message(
                            "Git HEAD now {}. Restart the application; "
                            "rerun setup if dependencies changed."
                            .format(value.current[:12]))
                        self.status.set("Git update completed")
                        messagebox.showinfo(
                            "Git updater",
                            "Source checkout updated safely.\n"
                            "Restart twrpdtgen-NEXT to load the new code.",
                            parent=self.root)
                    elif kind == "done":
                        self.result = value
                        self.status.set("Completed — source generated; flash safety not verified")
                        self._message("Completed successfully.")
                        messagebox.showinfo(
                            "Finished", "Files were written successfully.\n"
                            "Recovery bootability and flash safety remain unverified.",
                            parent=self.root)
                    else:
                        self.last_git_status = None
                        self.git_status_text.set(
                            "Update state unknown · Check for updates again")
                        self.status.set("Failed — check the log")
                        self._message("ERROR: " + str(value))
                        messagebox.showerror("Operation failed", str(value), parent=self.root)
                    self._sync_update_controls()
        except queue.Empty:
            pass
        if self.busy:
            self.root.after(100, self._poll)

    def _close(self):
        from tkinter import messagebox
        if self.busy:
            messagebox.showwarning(
                "Generation in progress",
                "Finish the current operation before closing the window.",
                parent=self.root)
        else:
            self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="twrpdtgen-gui",
        description="Graphical twrpdtgen-NEXT image / TWRP tree generator")
    parser.add_argument('input', nargs='?', type=Path,
                        help='optional source image/folder')
    parser.add_argument('--gui', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--tk', action='store_true',
                        help='force legacy Tk interface instead of PyQt5')
    parser.add_argument(
        "--source", type=Path,
        help="prefill the firmware source image/archive/folder")
    parser.add_argument(
        "--output", type=Path,
        help="prefill the generated tree destination")
    args = parser.parse_args(argv)
    if not args.tk:
        from twrpdtgen.qtgui import qt_available, main as qt_main
        if qt_available():
            options = []
            if args.source or args.input:
                options += ["--source", str(args.source or args.input)]
            if args.output:
                options += ["--output", str(args.output)]
            return qt_main(options)
    if not can_launch_gui():
        parser.exit(
            2, "GUI unavailable. Install Tk and start a graphical desktop, "
            "or use twrpdtgen-cli (or launcher.cmd --cli).\n")
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        parser.exit(
            2, "Could not open a desktop window: {}. Use twrpdtgen-cli.\n".format(exc))
    NextWindow(root, args.source or args.input, args.output)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
