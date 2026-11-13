# SPDX-License-Identifier: Apache-2.0
"""Conservative Git checkout updater for twrpdtgen-NEXT.

No force/reset/stash, no destructive working-tree changes, and no updates to
pip wheel/ZIP installations. Updates require an explicitly requested fast
forward of the configured upstream, and never run automatically on startup.
"""
from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
import json
import shutil
import subprocess

from twrpdtgen import module_path


class GitUpdateError(RuntimeError):
    """Safely abort an unsupported or conflicting update."""


@dataclass(frozen=True)
class UpdateStatus:
    root: str
    branch: str
    upstream: str
    current: str
    latest: str
    ahead: int
    behind: int
    dirty: bool

    @property
    def available(self) -> bool:
        return self.behind > 0

    @property
    def can_apply(self) -> bool:
        return self.behind > 0 and self.ahead == 0 and not self.dirty

    @property
    def state(self) -> str:
        """A single consistent status for the CLI and every GUI."""
        if self.dirty:
            return "local_changes"
        if self.ahead and self.behind:
            return "diverged"
        if self.ahead:
            return "ahead"
        if not self.behind:
            return "up_to_date"
        return "update_available"

    @property
    def explanation(self) -> str:
        messages = {
            "local_changes": (
                "Local files are modified or untracked. Clean the working "
                "tree before updating; no changes will be overwritten."),
            "diverged": (
                "This branch has both local and upstream commits. "
                "Resolve divergence manually before updating."),
            "ahead": (
                "The local branch is ahead of upstream. Nothing will be "
                "checked out automatically."),
            "up_to_date": (
                "Already up to date. There is nothing new to check out."),
            "update_available": (
                "A clean, fast-forward update is available."),
        }
        return messages[self.state]

    def to_dict(self):
        value = asdict(self)
        value["available"] = self.available
        value["can_apply"] = self.can_apply
        value["state"] = self.state
        value["explanation"] = self.explanation
        return value


def checkout_root(root: Optional[Path] = None) -> Path:
    """Reject package installs that have no genuine project Git checkout."""
    path = Path(root if root is not None else module_path.parent).expanduser().resolve()
    if shutil.which("git") is None:
        raise GitUpdateError("Git is not installed or is not on PATH.")
    if not (path / "pyproject.toml").is_file() or not (
            path / "twrpdtgen" / "__init__.py").is_file():
        raise GitUpdateError(
            "Updater requires a twrpdtgen-NEXT source checkout with pyproject.toml. "
            "For a wheel/pip-only install, clone the project and launch it there.")
    top = _git(path, "rev-parse", "--show-toplevel")
    if Path(top).resolve() != path:
        raise GitUpdateError(
            "The package directory must be the Git checkout root. "
            "Refusing to update a parent or unrelated repository.")
    return path


def _git(root: Path, *args: str, timeout: int = 120) -> str:
    command = ["git", "-C", str(root), "-c", "fetch.recurseSubmodules=false",
               "-c", "submodule.recurse=false", *args]
    try:
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError as exc:
        raise GitUpdateError("Git was not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitUpdateError("Git operation exceeded {} seconds".format(
            timeout)) from exc
    if completed.returncode:
        description = (completed.stderr or completed.stdout).strip()
        raise GitUpdateError(
            "git {} failed: {}".format(args[0], description[:1200]))
    return completed.stdout.strip()


def _upstream(root: Path):
    branch = _git(root, "symbolic-ref", "-q", "--short", "HEAD")
    if not branch:
        raise GitUpdateError("Detached HEAD: switch to a tracking branch first.")
    try:
        upstream = _git(root, "rev-parse", "--abbrev-ref",
                        "--symbolic-full-name", "@{upstream}")
        remote = _git(root, "config", "--get", "branch.{}.remote".format(branch))
    except GitUpdateError as exc:
        raise GitUpdateError(
            "This branch has no configured upstream. Set one with "
            "'git branch --set-upstream-to origin/<branch>' first.") from exc
    if not remote or remote == ".":
        raise GitUpdateError("Updater requires a remote-tracking branch.")
    return branch, upstream, remote


def check_updates(root: Optional[Path] = None, *, fetch: bool = True) -> UpdateStatus:
    """Fetch configured remote and compare HEAD with its tracking ref.

    A check changes only Git's remote-tracking metadata, not project files.
    """
    path = checkout_root(root)
    branch, upstream, remote = _upstream(path)
    if fetch:
        _git(path, "fetch", "--prune", "--no-tags", remote, timeout=180)
    current = _git(path, "rev-parse", "HEAD")
    latest = _git(path, "rev-parse", upstream)
    counts = _git(path, "rev-list", "--left-right", "--count",
                  "HEAD...{}".format(upstream)).split()
    if len(counts) != 2:
        raise GitUpdateError("Cannot compare local and upstream commits")
    dirty = bool(_git(path, "status", "--porcelain", "--untracked-files=all"))
    return UpdateStatus(
        root=str(path), branch=branch, upstream=upstream,
        current=current, latest=latest, ahead=int(counts[0]),
        behind=int(counts[1]), dirty=dirty)


def apply_update(root: Optional[Path] = None, *, confirmed: bool = False) -> UpdateStatus:
    """Update only an explicitly confirmed clean, nondivergent checkout."""
    if not confirmed:
        raise GitUpdateError(
            "Update not confirmed. Choose Update in the GUI or use --apply.")
    path = checkout_root(root)
    status = check_updates(path, fetch=True)
    if status.dirty:
        raise GitUpdateError(
            "Local edits or untracked files were found. Commit, move, or "
            "back them up before updating; nothing was modified.")
    if status.ahead:
        raise GitUpdateError(
            "Local branch has {} unpushed commit(s). Fast-forward refused; "
            "resolve the branch history manually.".format(status.ahead))
    if not status.available:
        raise GitUpdateError(
            "Already up to date. There is nothing new to check out; "
            "no Git merge or checkout was performed.")
    # Recheck tracked and untracked files immediately before merging.
    if _git(path, "status", "--porcelain", "--untracked-files=all"):
        raise GitUpdateError("Working tree changed; update cancelled.")
    _git(path, "merge", "--ff-only", status.upstream)
    finished = check_updates(path, fetch=False)
    if finished.current != status.latest:
        raise GitUpdateError("Git merge completed at an unexpected commit.")
    return finished


def main(argv=None):
    parser = ArgumentParser(
        prog="twrpdtgen-update",
        description="Check or fast-forward the twrpdtgen-NEXT source checkout")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true",
                       help="fetch and compare with upstream (default)")
    group.add_argument("--apply", action="store_true",
                       help="explicitly fast-forward clean tracked checkout")
    parser.add_argument("--repo", type=Path, default=None,
                        help="source checkout; default is this package's repo")
    parser.add_argument("--json", action="store_true",
                        help="print structured results")
    parser.add_argument("--offline", action="store_true",
                        help="check cached refs only (not valid with --apply)")
    args = parser.parse_args(argv)
    if args.offline and args.apply:
        parser.error("--offline cannot be combined with --apply")
    try:
        status = (
            apply_update(args.repo, confirmed=True) if args.apply
            else check_updates(args.repo, fetch=not args.offline)
        )
    except GitUpdateError as exc:
        parser.exit(2, "Git updater: {}\n".format(exc))
    if args.json:
        print(json.dumps(status.to_dict(), indent=2))
    else:
        print("Checkout: {}".format(status.root))
        print("Branch: {} → {}".format(status.branch, status.upstream))
        print("HEAD: {}".format(status.current[:12]))
        print("Upstream: {}".format(status.latest[:12]))
        print("Behind: {} | Ahead: {} | Local edits: {}".format(
            status.behind, status.ahead, "yes" if status.dirty else "no"))
        if args.apply:
            print("Successfully fast-forwarded to new upstream commits.")
            print("Restart twrpdtgen-NEXT; reinstall dependencies if required.")
        else:
            print(status.explanation)
            if status.can_apply:
                print("To update, run: twrpdtgen-update --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
