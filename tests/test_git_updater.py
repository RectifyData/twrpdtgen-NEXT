# SPDX-License-Identifier: Apache-2.0
"""Local Git integration tests: no network or real project updates."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from twrpdtgen.git_updater import (
    GitUpdateError, apply_update, check_updates, checkout_root,
)


@unittest.skipUnless(shutil.which("git"), "Git required for updater tests")
class GitUpdaterTests(unittest.TestCase):
    def git(self, root, *args):
        process = subprocess.run(
            ["git", "-C", str(root), *args], text=True,
            encoding="utf-8", errors="replace",
            capture_output=True, check=False)
        if process.returncode:
            self.fail("Git failed: {} {}: {}".format(
                root, args, process.stderr))
        return process.stdout.strip()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="twrpdtgen-updater-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.remote = self.base / "upstream.git"
        self.work = self.base / "work"
        self.peer = self.base / "peer"

        self.git(self.base, "init", "--bare", "-b", "main", str(self.remote))
        self.git(self.base, "clone", str(self.remote), str(self.work))
        self.git(self.work, "config", "user.name", "NEXT CI")
        self.git(self.work, "config", "user.email", "next-ci@example.invalid")
        (self.work / "twrpdtgen").mkdir()
        (self.work / "twrpdtgen" / "__init__.py").write_text(
            '__version__ = "0.0.0"\n')
        (self.work / "pyproject.toml").write_text(
            '[tool.poetry]\nname="twrpdtgen"\n')
        self.git(self.work, "add", ".")
        self.git(self.work, "commit", "-m", "initial generator")
        self.git(self.work, "push", "-u", "origin", "main")

        self.git(self.base, "clone", str(self.remote), str(self.peer))
        self.git(self.peer, "config", "user.name", "NEXT CI")
        self.git(self.peer, "config", "user.email", "next-ci@example.invalid")

    def peer_commit(self, message="upstream"):
        (self.peer / "new-feature.txt").write_text(message + "\n")
        self.git(self.peer, "add", ".")
        self.git(self.peer, "commit", "-m", message)
        self.git(self.peer, "push", "origin", "main")

    def test_check_and_confirmed_fast_forward_without_overwriting_work(self):
        original = self.git(self.work, "rev-parse", "HEAD")
        self.peer_commit()
        status = check_updates(self.work)
        self.assertTrue(status.available)
        self.assertTrue(status.can_apply)
        self.assertEqual(status.behind, 1)
        self.assertFalse(status.dirty)
        self.assertEqual(self.git(self.work, "rev-parse", "HEAD"), original)
        with self.assertRaisesRegex(GitUpdateError, "not confirmed"):
            apply_update(self.work)
        applied = apply_update(self.work, confirmed=True)
        self.assertEqual(applied.behind, 0)
        self.assertEqual(applied.ahead, 0)
        self.assertEqual(self.git(self.work, "rev-parse", "HEAD"),
                         self.git(self.peer, "rev-parse", "HEAD"))
        self.assertEqual(
            (self.work / "new-feature.txt").read_text(), "upstream\n")

    def test_local_edits_are_refused_without_stashing_or_resetting(self):
        self.peer_commit()
        (self.work / "user-notes.txt").write_text("keep this file\n")
        before = self.git(self.work, "rev-parse", "HEAD")
        status = check_updates(self.work)
        self.assertTrue(status.dirty)
        self.assertFalse(status.can_apply)
        with self.assertRaisesRegex(GitUpdateError, "Local edits"):
            apply_update(self.work, confirmed=True)
        self.assertEqual((self.work / "user-notes.txt").read_text(),
                         "keep this file\n")
        self.assertEqual(before, self.git(self.work, "rev-parse", "HEAD"))

    def test_diverged_branches_do_not_get_forced(self):
        (self.work / "local.txt").write_text("my local commit\n")
        self.git(self.work, "add", "local.txt")
        self.git(self.work, "commit", "-m", "local change")
        current = self.git(self.work, "rev-parse", "HEAD")
        self.peer_commit()
        status = check_updates(self.work)
        self.assertEqual(status.ahead, 1)
        self.assertEqual(status.behind, 1)
        self.assertFalse(status.can_apply)
        with self.assertRaisesRegex(GitUpdateError, "unpushed"):
            apply_update(self.work, confirmed=True)
        self.assertEqual(current, self.git(self.work, "rev-parse", "HEAD"))
        self.assertEqual(
            (self.work / "local.txt").read_text(), "my local commit\n")

    def test_installed_packages_and_unrelated_parent_repos_refused(self):
        nonrepo = self.base / "not-a-project"
        nonrepo.mkdir()
        with self.assertRaises(GitUpdateError):
            checkout_root(nonrepo)
        nested = self.work / "somewhere"
        nested.mkdir()
        with self.assertRaises(GitUpdateError):
            checkout_root(nested)

    def test_up_to_date_update_is_blocked_without_running_merge(self):
        from unittest.mock import patch
        status = check_updates(self.work)
        self.assertFalse(status.available)
        self.assertFalse(status.can_apply)
        self.assertEqual(status.state, "up_to_date")
        self.assertIn("nothing new", status.explanation.lower())
        current = self.git(self.work, "rev-parse", "HEAD")
        with patch("twrpdtgen.git_updater._git", wraps=__import__(
                "twrpdtgen.git_updater", fromlist=["_git"])._git) as invoke:
            with self.assertRaisesRegex(GitUpdateError, "Already up to date"):
                apply_update(self.work, confirmed=True)
            self.assertFalse(any(
                call.args[1] in ("merge", "checkout", "reset", "stash")
                for call in invoke.call_args_list))
        self.assertEqual(current, self.git(self.work, "rev-parse", "HEAD"))
        self.assertEqual(status.to_dict()["state"], "up_to_date")

    def test_status_explains_why_updates_are_not_allowed(self):
        from twrpdtgen.git_updater import UpdateStatus
        values = dict(root="/tmp/test", branch="main", upstream="origin/main",
                      current="a" * 40, latest="a" * 40)
        dirty = UpdateStatus(**values, ahead=0, behind=0, dirty=True)
        self.assertEqual(dirty.state, "local_changes")
        self.assertFalse(dirty.can_apply)
        ahead = UpdateStatus(**values, ahead=1, behind=0, dirty=False)
        self.assertEqual(ahead.state, "ahead")
        divergent = UpdateStatus(**values, ahead=1, behind=1, dirty=False)
        self.assertEqual(divergent.state, "diverged")
        self.assertFalse(divergent.can_apply)
        available = UpdateStatus(**values, ahead=0, behind=1, dirty=False)
        self.assertEqual(available.state, "update_available")
        self.assertTrue(available.can_apply)

    def test_offline_check_does_not_fetch(self):
        self.peer_commit()
        status = check_updates(self.work, fetch=False)
        self.assertEqual(status.behind, 0)
        self.assertFalse(status.available)
        current = check_updates(self.work, fetch=True)
        self.assertEqual(current.behind, 1)


if __name__ == "__main__":
    unittest.main()
