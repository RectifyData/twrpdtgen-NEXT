# SPDX-License-Identifier: Apache-2.0
"""Optional PyQt5 desktop frontend for twrpdtgen-NEXT.

Qt is deliberately an optional package extra. The CLI, Android/Termux
web frontend and Tk fallback remain usable without PyQt5 installed.
"""
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import importlib.util
import os
import sys

from twrpdtgen import __version__
from twrpdtgen.gui import open_folder, parse_job, run_job
from twrpdtgen.option_sync import interface_schema


def qt_available():
    if sys.platform != "win32" and not (
            os.environ.get("DISPLAY")
            or os.environ.get("WAYLAND_DISPLAY")
            or os.environ.get("QT_QPA_PLATFORM") == "offscreen"):
        return False
    try:
        return importlib.util.find_spec("PyQt5.QtWidgets") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def create_window(initial_source=None, initial_output=None):
    """Construct a native QWidget using the same shared CLI/GUI settings."""
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout,
        QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
        QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
        QScrollArea, QToolButton, QVBoxLayout, QWidget,
    )

    class TaskThread(QThread):
        message = pyqtSignal(str)
        success = pyqtSignal(object)
        failure = pyqtSignal(str)

        def __init__(self, kind, job=None, parent=None):
            super().__init__(parent)
            self.kind = kind
            self.job = job

        def run(self):
            try:
                if self.kind == "generate":
                    self.success.emit(run_job(self.job, report=self.message.emit))
                else:
                    from twrpdtgen.git_updater import check_updates, apply_update
                    if self.kind == "check":
                        self.message.emit("Checking configured Git upstream...")
                        status = check_updates()
                    else:
                        self.message.emit("Fast-forwarding clean Git checkout...")
                        status = apply_update(confirmed=True)
                    self.success.emit(status)
            except Exception as exc:
                self.failure.emit("{}: {}".format(type(exc).__name__, exc))

    class QtWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("twrpdtgen-NEXT {} · Recovery Tree Studio (PyQt5)".format(__version__))
            self.resize(1024, 800)
            self.setMinimumSize(620, 500)
            self.schema = interface_schema()
            self.fields = {}
            self.extras = {}
            self.flags = {}
            self.busy = False
            self.task = None
            self.result = None

            main = QWidget()
            outer = QVBoxLayout(main)
            outer.setContentsMargins(16, 12, 16, 12)
            outer.setSpacing(10)
            self.setCentralWidget(main)

            top = QHBoxLayout()
            name = QLabel("Recovery Tree Studio")
            name.setObjectName("title")
            top.addWidget(name)
            top.addStretch(1)
            top.addWidget(QLabel("PyQt5 · v{}".format(__version__)))
            self.tools = QToolButton(self)
            self.tools.setText("Tools  ⋮")
            self.tools.setPopupMode(QToolButton.InstantPopup)
            menu = QMenu(self.tools)
            menu.addAction("Check Git updates", self.check_updates)
            menu.addAction("Update from Git…", self.apply_update)
            menu.addSeparator()
            menu.addAction("Open output folder", self.open_output)
            menu.addAction("Copy logs", self.copy_logs)
            menu.addAction("About & safety", self.about)
            self.tools.setMenu(menu)
            top.addWidget(self.tools)
            outer.addLayout(top)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            content = QWidget()
            body = QVBoxLayout(content)
            body.setContentsMargins(4, 4, 4, 12)
            body.setSpacing(12)
            scroll.setWidget(content)
            outer.addWidget(scroll, stretch=1)

            inputs = QGroupBox("1 · Firmware source")
            ins = QFormLayout(inputs)
            self.add_path(ins, "source", "Image / archive / folder",
                          str(initial_source or ""), folder_choice=True)
            body.addWidget(inputs)

            companions = QGroupBox("2 · Optional companion boot images")
            cp = QFormLayout(companions)
            for key, label in (
                    ("boot_image", "boot.img"),
                    ("vendor_boot", "vendor_boot.img"),
                    ("init_boot", "init_boot.img")):
                self.add_path(cp, key, label)
            body.addWidget(companions)

            destination = QGroupBox("3 · Output")
            dest = QFormLayout(destination)
            self.add_path(dest, "output", "Output directory",
                          str(initial_output or Path.home() / "TWRP-Trees"),
                          directory=True)
            self.add_path(dest, "archive", "ZIP location (optional)", save=True)
            self.add_combo(dest, "mode", "Action",
                           ["tree", "extract"], default="tree")
            body.addWidget(destination)

            options = QGroupBox("4 · Recovery configuration")
            opts = QFormLayout(options)
            for key, label in (
                    ("skeleton", "TWRP profile"),
                    ("recovery_layout", "Recovery source"),
                    ("recovery_root_mode", "Ramdisk overlay")):
                definition = self.schema["choices"][key]
                self.add_combo(opts, key, label, definition["choices"],
                               definition["default"])
            self.add_text(opts, "recovery_fragment",
                          "Verified vendor fragment")
            for key, label in (
                    ("boot_size", "Verified boot partition size"),
                    ("recovery_size", "Verified recovery partition size"),
                    ("super_size", "Verified super partition size"),
                    ("dynamic_group_size", "Verified dynamic group size")):
                self.add_text(opts, key, label, "e.g. 64MiB (optional)")
            note = QLabel(
                "Blank size fields use provisional source-image limits; "
                "verify the physical GPT/lpdump capacity before flashing.")
            note.setWordWrap(True)
            opts.addRow(note)
            body.addWidget(options)

            advanced = QGroupBox("5 · CLI options (synchronized automatically)")
            advanced_layout = QFormLayout(advanced)
            if not self.schema["extras"]:
                advanced_layout.addRow(QLabel("All generator options are already shown."))
            for item in self.schema["extras"]:
                key = item["name"]
                if item["kind"] == "boolean":
                    widget = QCheckBox(item["flag"] + " — " + item["label"])
                    widget.setChecked(bool(item["default"]))
                    advanced_layout.addRow(widget)
                elif item["kind"] == "choice":
                    widget = QComboBox()
                    widget.addItems(item["choices"])
                    widget.setCurrentText(item["default"])
                    advanced_layout.addRow(item["flag"], widget)
                else:
                    widget = QLineEdit(str(item["default"]))
                    widget.setPlaceholderText(item["label"])
                    advanced_layout.addRow(item["flag"], widget)
                self.extras[key] = widget
            body.addWidget(advanced)

            flags = QGroupBox("Safety and packaging")
            flag_layout = QVBoxLayout(flags)
            for key, label in (
                    ("overwrite", "Replace an existing tree (confirmation required)"),
                    ("include_stock_root", "Include full stock ramdisk in ZIP")):
                widget = QCheckBox(label)
                self.flags[key] = widget
                flag_layout.addWidget(widget)
            flag_layout.addWidget(QLabel(
                "A generated tree is source only — never automatically flashed."))
            body.addWidget(flags)

            updates = QGroupBox("Git updater")
            up = QHBoxLayout(updates)
            self.check_button = QPushButton("Check for updates")
            self.check_button.clicked.connect(self.check_updates)
            self.update_button = QPushButton("Update from Git…")
            self.update_button.clicked.connect(self.apply_update)
            up.addWidget(self.check_button)
            up.addWidget(self.update_button)
            up.addStretch()
            body.addWidget(updates)
            body.addStretch()

            footer = QHBoxLayout()
            self.go_button = QPushButton("Generate / Extract")
            self.go_button.setObjectName("primary")
            self.go_button.clicked.connect(self.generate)
            footer.addWidget(self.go_button)
            self.open_button = QPushButton("Open output")
            self.open_button.clicked.connect(self.open_output)
            footer.addWidget(self.open_button)
            self.progress = QProgressBar()
            self.progress.setRange(0, 0)
            self.progress.hide()
            footer.addWidget(self.progress, stretch=1)
            outer.addLayout(footer)
            self.status = QLabel("Ready. Select a firmware image to begin.")
            outer.addWidget(self.status)
            self.log = QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setMaximumBlockCount(500)
            self.log.setFixedHeight(158)
            outer.addWidget(self.log)
            self.append_log("Desktop GUI and CLI share the same generator.")

        def add_text(self, layout, key, label, hint=""):
            field = QLineEdit()
            field.setPlaceholderText(hint)
            self.fields[key] = field
            layout.addRow(label, field)

        def add_combo(self, layout, key, label, choices, default):
            widget = QComboBox()
            widget.addItems([str(x) for x in choices])
            widget.setCurrentText(str(default))
            self.fields[key] = widget
            layout.addRow(label, widget)

        def add_path(self, layout, key, label, default="", *,
                     folder_choice=False, directory=False, save=False):
            field = QLineEdit(str(default))
            self.fields[key] = field
            row = QWidget()
            items = QHBoxLayout(row)
            items.setContentsMargins(0, 0, 0, 0)
            items.addWidget(field, stretch=1)

            def pick_file():
                chosen, _ = QFileDialog.getOpenFileName(
                    self, "Select Android firmware image", str(Path.home()),
                    "Firmware files (*.img *.lz4 *.zip *.tar *.md5 *.gz *.xz *.tgz);;All files (*)")
                if chosen:
                    field.setText(chosen)

            def pick_folder():
                chosen = QFileDialog.getExistingDirectory(
                    self, "Choose folder", str(Path.home()))
                if chosen:
                    field.setText(chosen)

            def pick_save():
                chosen, _ = QFileDialog.getSaveFileName(
                    self, "Save generated ZIP", str(Path.home()), "ZIP archive (*.zip)")
                if chosen:
                    field.setText(chosen)

            button = QPushButton("Browse…")
            button.clicked.connect(
                pick_save if save else pick_folder if directory else pick_file)
            items.addWidget(button)
            if folder_choice:
                folder = QPushButton("Folder…")
                folder.clicked.connect(pick_folder)
                items.addWidget(folder)
            layout.addRow(label, row)

        def values(self):
            values = {}
            for key, widget in self.fields.items():
                values[key] = (
                    widget.currentText() if isinstance(widget, QComboBox)
                    else widget.text())
            values.update({key: box.isChecked()
                           for key, box in self.flags.items()})
            values["cli_options"] = {
                key: (widget.isChecked() if isinstance(widget, QCheckBox)
                      else widget.currentText() if isinstance(widget, QComboBox)
                      else widget.text())
                for key, widget in self.extras.items()
            }
            return values

        def append_log(self, text):
            self.log.appendPlainText(str(text))
            self.status.setText(str(text))

        def busy_state(self, running):
            self.busy = running
            self.go_button.setEnabled(not running)
            self.check_button.setEnabled(not running)
            self.update_button.setEnabled(not running)
            self.progress.setVisible(running)

        def launch_task(self, kind, job=None):
            if self.busy:
                return
            self.busy_state(True)
            self.task = TaskThread(kind, job=job, parent=self)
            self.task.message.connect(self.append_log)
            self.task.success.connect(
                lambda value: self.task_done(kind, value))
            self.task.failure.connect(self.task_failed)
            self.task.finished.connect(self.task.deleteLater)
            self.task.start()

        def generate(self):
            try:
                job = parse_job(self.values())
            except Exception as exc:
                QMessageBox.critical(self, "Invalid settings", str(exc))
                return
            if job.overwrite and QMessageBox.question(
                    self, "Replace generated tree?",
                    "This may replace an existing generated tree. Continue?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) != QMessageBox.Yes:
                return
            self.append_log("Starting {}...".format(job.mode))
            self.launch_task("generate", job)

        def check_updates(self):
            self.launch_task("check")

        def apply_update(self):
            if self.busy:
                return
            if QMessageBox.question(
                    self, "Confirm Git update",
                    "Fetch and fast-forward this source checkout from its "
                    "configured upstream?\n\nUncommitted work and diverged "
                    "branches are never overwritten. Restart after updating.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) != QMessageBox.Yes:
                return
            self.launch_task("update")

        def task_done(self, kind, value):
            self.busy_state(False)
            if kind == "generate":
                self.result = value
                self.append_log("Completed. Candidate sources are not flash-validated.")
                QMessageBox.information(
                    self, "Completed", "Tree/extraction produced.\n"
                    "Check bootability, AVB, partition geometry and encryption "
                    "before flashing.")
            elif kind == "check":
                self.append_log(
                    "Git upstream {}: {} new / {} local commits, dirty={}."
                    .format(value.upstream, value.behind,
                            value.ahead, value.dirty))
                if value.can_apply:
                    self.append_log("Update available. Use Update from Git.")
                elif value.available:
                    self.append_log("Update blocked until branch conflicts/edits are resolved.")
                else:
                    self.append_log("Up to date.")
            else:
                self.append_log("Git HEAD: {}".format(value.current[:12]))
                QMessageBox.information(
                    self, "Git update", "Checked out the latest allowed source.\n"
                    "Restart twrpdtgen-NEXT and rerun setup if dependencies changed.")

        def task_failed(self, error):
            self.busy_state(False)
            self.append_log("ERROR: " + str(error))
            QMessageBox.critical(self, "Operation failed", str(error))

        def open_output(self):
            try:
                target = (
                    self.result.tree or self.result.extracted
                    if self.result else None)
                if not target:
                    target = Path(self.fields["output"].text()).expanduser()
                open_folder(target)
            except Exception as exc:
                QMessageBox.warning(self, "Cannot open output", str(exc))

        def copy_logs(self):
            QApplication.clipboard().setText(self.log.toPlainText())

        def about(self):
            QMessageBox.information(
                self, "About twrpdtgen-NEXT",
                "twrpdtgen-NEXT {} · PyQt5\n\nThe desktop, Android GUI and "
                "CLI use the same option schema and parser. Updates require "
                "confirmation and a clean fast-forward checkout.\n\n"
                "TWRP sources are not necessarily bootable.".format(__version__))

        def closeEvent(self, event):
            if self.busy:
                QMessageBox.warning(
                    self, "Operation in progress",
                    "Finish the current operation before exiting.")
                event.ignore()
            else:
                event.accept()

    return QtWindow()


def main(argv=None):
    parser = ArgumentParser(
        prog="twrpdtgen-qt", description="Optional PyQt5 recovery tree GUI")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not qt_available():
        parser.exit(
            2, "PyQt5 desktop unavailable. Install 'twrpdtgen[qt]' on a "
            "graphical system or use twrpdtgen-gui for the Tk fallback.\n")
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance()
    owns = app is None
    if app is None:
        app = QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget { background: #111a2a; color: #e6effe; font-size: 12px; }
        QLineEdit, QComboBox, QPlainTextEdit {
            background: #101e33; border: 1px solid #3b5478;
            padding: 7px; border-radius: 6px;
        }
        QGroupBox {
            border: 1px solid #324763; margin-top: 11px; padding-top: 12px;
            border-radius: 7px; font-weight: 600;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; }
        QPushButton, QToolButton {
            background: #29486f; border: 1px solid #5276a3; padding: 8px;
            border-radius: 7px;
        }
        QPushButton:hover, QToolButton:hover { background: #365b89; }
        QPushButton#primary { background: #3a72c4; font-weight: bold; }
        QLabel#title { font-size: 21px; font-weight: bold; }
        QScrollArea { border: 0; }
    """)
    window = create_window(args.source, args.output)
    window.show()
    return app.exec_() if owns else 0


if __name__ == "__main__":
    raise SystemExit(main())
