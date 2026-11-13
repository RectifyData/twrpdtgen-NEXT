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
        QScrollArea, QTabWidget, QToolButton, QVBoxLayout, QWidget,
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
            self.setWindowTitle("twrpdtgen NEXT {}".format(__version__))
            self.resize(920, 720)
            self.setMinimumSize(620, 500)
            self.schema = interface_schema()
            self.fields = {}
            self.extras = {}
            self.flags = {}
            self.busy = False
            self.task = None
            self.result = None
            self.last_git_status = None

            main = QWidget()
            main.setObjectName("appRoot")
            outer = QVBoxLayout(main)
            outer.setContentsMargins(12, 10, 12, 10)
            outer.setSpacing(8)
            self.setCentralWidget(main)

            header = QFrame()
            header.setObjectName("appHeader")
            top = QHBoxLayout(header)
            top.setContentsMargins(2, 3, 2, 6)
            heading = QVBoxLayout()
            heading.setSpacing(3)
            name = QLabel("twrpdtgen NEXT")
            name.setObjectName("title")
            heading.addWidget(name)
            tagline = QLabel("TWRP device tree generator · {}".format(__version__))
            tagline.setObjectName("subtitle")
            heading.addWidget(tagline)
            top.addLayout(heading)
            top.addStretch(1)
            self.tools = QToolButton(self)
            self.tools.setText("Tools")
            self.tools.setPopupMode(QToolButton.InstantPopup)
            menu = QMenu(self.tools)
            menu.addAction("Check Git updates", self.check_updates)
            self.update_action = menu.addAction("Update from Git…", self.apply_update)
            self.update_action.setEnabled(False)
            menu.addSeparator()
            menu.addAction("Open output folder", self.open_output)
            menu.addAction("Copy logs", self.copy_logs)
            menu.addAction("About & safety", self.about)
            self.tools.setMenu(menu)
            top.addWidget(self.tools)
            outer.addWidget(header)

            # Keep the everyday workflow compact. Advanced settings and the
            # updater live on separate pages, rather than one long scroll.
            self.tabs = QTabWidget()
            self.tabs.setObjectName("workspaceTabs")
            outer.addWidget(self.tabs, stretch=1)

            def add_page(title):
                page = QWidget()
                wrapper = QVBoxLayout(page)
                wrapper.setContentsMargins(0, 8, 0, 0)
                scroll = QScrollArea(page)
                scroll.setObjectName("formScroll")
                scroll.setWidgetResizable(True)
                content = QWidget()
                layout = QVBoxLayout(content)
                layout.setContentsMargins(4, 4, 8, 6)
                layout.setSpacing(9)
                scroll.setWidget(content)
                wrapper.addWidget(scroll)
                self.tabs.addTab(page, title)
                return layout

            build_body = add_page("Generate")
            advanced_body = add_page("Settings")
            update_body = add_page("Updates")

            inputs = QGroupBox("Source")
            ins = QFormLayout(inputs)
            self.add_path(ins, "source", "Image / archive / folder",
                          str(initial_source or ""), folder_choice=True)
            build_body.addWidget(inputs)

            companions = QGroupBox("Additional images")
            cp = QFormLayout(companions)
            for key, label in (
                    ("boot_image", "boot.img"),
                    ("vendor_boot", "vendor_boot.img"),
                    ("init_boot", "init_boot.img")):
                self.add_path(cp, key, label)
            build_body.addWidget(companions)

            destination = QGroupBox("Output")
            dest = QFormLayout(destination)
            self.add_path(dest, "output", "Output directory",
                          str(initial_output or Path.home() / "TWRP-Trees"),
                          directory=True)
            self.add_path(dest, "archive", "ZIP location (optional)", save=True)
            self.add_combo(dest, "mode", "Action",
                           ["tree", "extract"], default="tree")
            build_body.addWidget(destination)

            options = QGroupBox("Recovery")
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
                self.add_text(opts, key, label, "Known size only, e.g. 64MiB")
            note = QLabel(
                "Leave unknown sizes blank. NEXT no longer uses image lengths "
                "as partition capacities.")
            note.setWordWrap(True)
            opts.addRow(note)
            advanced_body.addWidget(options)

            advanced = QGroupBox("Other options")
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
            advanced_body.addWidget(advanced)

            flags = QGroupBox("Export")
            flag_layout = QVBoxLayout(flags)
            for key, label in (
                    ("overwrite", "Overwrite existing output (confirm first)"),
                    ("include_stock_root", "Include stock ramdisk in ZIP")):
                widget = QCheckBox(label)
                self.flags[key] = widget
                flag_layout.addWidget(widget)
            flag_layout.addWidget(QLabel(
                "Generated source is not a boot-tested recovery."))
            build_body.addWidget(flags)

            updates = QGroupBox("Git updates")
            up_layout = QVBoxLayout(updates)
            up_layout.setSpacing(12)
            self.git_status_badge = QLabel("Not checked")
            self.git_status_badge.setObjectName("updateBadge")
            up_layout.addWidget(self.git_status_badge)
            self.git_details = QLabel(
                "Check the configured upstream to see whether new commits "
                "are available. Updating is disabled until a valid "
                "fast-forward update has been verified.")
            self.git_details.setObjectName("updateDetails")
            self.git_details.setWordWrap(True)
            up_layout.addWidget(self.git_details)
            up_buttons = QHBoxLayout()
            self.check_button = QPushButton("Check for updates")
            self.check_button.clicked.connect(self.check_updates)
            self.update_button = QPushButton("Update from Git…")
            self.update_button.clicked.connect(self.apply_update)
            self.update_button.setEnabled(False)
            up_buttons.addWidget(self.check_button)
            up_buttons.addWidget(self.update_button)
            up_buttons.addStretch()
            up_layout.addLayout(up_buttons)
            safety = QLabel(
                "Only an explicit fast-forward of a clean Git checkout is "
                "allowed. No reset, stash, or checkout will run when "
                "already up to date. Restart to use updated source.")
            safety.setObjectName("hint")
            safety.setWordWrap(True)
            up_layout.addWidget(safety)
            update_body.addWidget(updates)
            build_body.addStretch()
            advanced_body.addStretch()
            update_body.addStretch()

            footer = QHBoxLayout()
            self.go_button = QPushButton("Generate tree")
            self.go_button.setObjectName("primary")
            self.go_button.clicked.connect(self.generate)
            self.fields["mode"].currentTextChanged.connect(
                lambda mode: self.go_button.setText(
                    "Extract files" if mode == "extract" else "Generate tree"))
            footer.addWidget(self.go_button)
            self.open_button = QPushButton("Open output")
            self.open_button.clicked.connect(self.open_output)
            footer.addWidget(self.open_button)
            self.progress = QProgressBar()
            self.progress.setRange(0, 0)
            self.progress.hide()
            footer.addWidget(self.progress, stretch=1)
            outer.addLayout(footer)
            self.status = QLabel("Ready")
            outer.addWidget(self.status)
            self.log = QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setMaximumBlockCount(500)
            self.log.setFixedHeight(110)
            outer.addWidget(self.log)
            self.append_log("Select a source image to begin.")

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
            can_update = bool(
                not running and self.last_git_status is not None
                and self.last_git_status.can_apply)
            self.update_button.setEnabled(can_update)
            self.update_action.setEnabled(can_update)
            self.progress.setVisible(running)

        def set_git_status(self, status=None, *, error=None):
            """Keep the status label and both update affordances in sync."""
            self.last_git_status = status
            if error:
                headline = "CHECK FAILED"
                detail = str(error)
            elif status is None:
                headline = "NOT CHECKED"
                detail = "Check for updates to enable Git actions."
            elif status.can_apply:
                headline = "UPDATE AVAILABLE"
                detail = (
                    "{} new commit(s) on {}. You can safely fast-forward."
                    .format(status.behind, status.upstream))
            else:
                labels = {
                    "up_to_date": "UP TO DATE",
                    "local_changes": "LOCAL CHANGES",
                    "diverged": "DIVERGED",
                    "ahead": "LOCAL BRANCH AHEAD",
                }
                headline = labels.get(status.state, "NO SAFE UPDATE")
                detail = status.explanation
            self.git_status_badge.setText(headline)
            self.git_details.setText(detail)
            self.busy_state(self.busy)

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
            if self.busy:
                return
            self.set_git_status()
            self.launch_task("check")

        def apply_update(self):
            if self.busy:
                return
            if self.last_git_status is None or not self.last_git_status.can_apply:
                self.tabs.setCurrentIndex(2)
                self.append_log(
                    self.last_git_status.explanation
                    if self.last_git_status is not None
                    else "Check for updates first. No update was performed.")
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
                self.set_git_status(value)
                self.tabs.setCurrentIndex(2)
                self.append_log(
                    "{} · {} behind, {} ahead, dirty={}."
                    .format(value.state, value.behind, value.ahead,
                            value.dirty))
            else:
                self.set_git_status(value)
                self.append_log("Updated Git HEAD: {}".format(value.current[:12]))
                QMessageBox.information(
                    self, "Git update completed",
                    "New upstream commits were fast-forwarded successfully.\n"
                    "Restart twrpdtgen-NEXT and rerun setup if dependencies changed.")

        def task_failed(self, error):
            self.busy_state(False)
            self.set_git_status(error=error)
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
    # Use the native OS widget theme; avoid a hardcoded card-heavy skin.
    window = create_window(args.source, args.output)
    window.show()
    return app.exec_() if owns else 0


if __name__ == "__main__":
    raise SystemExit(main())
