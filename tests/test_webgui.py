# SPDX-License-Identifier: Apache-2.0
"""Mobile/browser GUI HTTP contract and security tests."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from twrpdtgen.gui import GUIResult
from twrpdtgen.webgui import LocalServer, WebHandler, WebState


class LocalWebGUITests(unittest.TestCase):
    def setUp(self):
        self.state = WebState()
        self.server = LocalServer(("127.0.0.1", 0), WebHandler)
        self.server.state = self.state
        self.address = "http://127.0.0.1:{}".format(self.server.server_port)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)
        if self.state.thread is not None:
            self.state.thread.join(timeout=5)
        self.state.temp.cleanup()

    def request(self, path, method="GET", data=None, headers=None):
        req = Request(self.address + path, data=data,
                      headers=headers or {}, method=method)
        return urlopen(req, timeout=10)

    def test_mobile_html_status_and_local_only_headers(self):
        with self.request("/") as res:
            page = res.read().decode()
            self.assertIn("viewport", page)
            self.assertIn("<h1>twrpdtgen NEXT</h1>", page)
            self.assertIn('id="cliSyncedOptions"', page)
            self.assertIn('fetch("/api/options"', page)
            self.assertIn('id="gitApply" disabled', page)
            self.assertIn('gitStatus?.can_apply', page)
            self.assertIn(self.state.token, page)
            self.assertEqual(res.headers["X-Frame-Options"], "DENY")
            self.assertEqual(res.headers["Cache-Control"], "no-store")
        with self.request("/api/status") as res:
            self.assertEqual(json.load(res)["status"], "idle")
        with self.assertRaises(HTTPError) as exc:
            self.request("/", headers={"Host": "some-other-site.test"})
        self.assertEqual(exc.exception.code, 403)

    def test_http_schema_tracks_new_cli_options(self):
        from twrpdtgen.main import build_parser
        with self.request("/api/options") as res:
            schema = json.load(res)
        self.assertEqual(res.status, 200)
        self.assertIn("init_boot", schema["choices"]["recovery_layout"]["choices"])
        self.assertIn("git", [item["name"] for item in schema["extras"]])

        modified = build_parser()
        modified.add_argument("--future-mode", choices=("alpha", "beta"),
                              default="alpha")
        with patch("twrpdtgen.main.build_parser", return_value=modified):
            with self.request("/api/options") as res:
                schema = json.load(res)
        self.assertIn("future_mode", [item["name"]
                                     for item in schema["extras"]])

    def test_invalid_cli_extra_cannot_reach_runner(self):
        image = self.state.workspace / "init_boot.img"
        image.write_bytes(b"stock")
        payload = json.dumps({
            "source": str(image),
            "output": str(self.state.workspace / "output"),
            "cli_options": {"unexpected_argument": "value"},
        }).encode()
        headers = {"X-CSRF-Token": self.state.token,
                   "Content-Type": "application/json"}
        with self.assertRaises(HTTPError) as exc:
            self.request("/api/start", "POST", payload, headers)
        self.assertEqual(exc.exception.code, 400)

    def test_post_and_upload_are_csrf_protected(self):
        values = json.dumps({
            "source": "/missing.img",
            "output": "/tmp/tree"}).encode()
        with self.assertRaises(HTTPError) as exc:
            self.request("/api/start", method="POST", data=values,
                         headers={"Content-Type": "application/json"})
        self.assertEqual(exc.exception.code, 403)
        with self.assertRaises(HTTPError) as exc:
            self.request("/api/upload?name=boot.img", method="PUT",
                         data=b"BOOT")
        self.assertEqual(exc.exception.code, 403)

    def test_file_picker_upload_stream_is_local_and_sanitized(self):
        headers = {"X-CSRF-Token": self.state.token,
                   "Content-Type": "application/octet-stream"}
        with self.request("/api/upload?name=init_boot.img", "PUT",
                          b"test-image", headers) as res:
            path = Path(json.load(res)["path"])
        self.assertEqual(path.read_bytes(), b"test-image")
        self.assertTrue(path.is_relative_to(self.state.workspace))
        with self.assertRaises(HTTPError) as exc:
            self.request("/api/upload?name=..%2Ffoo.img", "PUT",
                         b"bad", headers)
        self.assertEqual(exc.exception.code, 400)

    def test_git_updater_requires_token_confirmation_and_clean_state(self):
        from twrpdtgen.git_updater import UpdateStatus
        status = UpdateStatus(
            root="/tmp/checkout", branch="main", upstream="origin/main",
            current="a" * 40, latest="b" * 40,
            ahead=0, behind=1, dirty=False)
        headers = {"X-CSRF-Token": self.state.token,
                   "Content-Type": "application/json"}
        with self.assertRaises(HTTPError) as exc:
            self.request("/api/git/check", "POST", b"{}")
        self.assertEqual(exc.exception.code, 403)
        with self.assertRaises(HTTPError) as exc:
            self.request("/api/git/apply", "POST", b"{}", headers)
        self.assertEqual(exc.exception.code, 400)
        with patch("twrpdtgen.git_updater.check_updates",
                   return_value=status) as check:
            with self.request("/api/git/check", "POST", b"{}", headers) as res:
                value = json.load(res)
                self.assertTrue(value["can_apply"])
                self.assertEqual(value["behind"], 1)
                check.assert_called_once()
        with patch("twrpdtgen.git_updater.apply_update",
                   return_value=status) as apply:
            with self.request(
                    "/api/git/apply", "POST",
                    json.dumps({"confirmed": True}).encode(), headers) as res:
                self.assertEqual(json.load(res)["branch"], "main")
                apply.assert_called_once_with(confirmed=True)

    def test_up_to_date_apply_is_rejected_without_any_checkout(self):
        from twrpdtgen.git_updater import GitUpdateError
        headers = {"X-CSRF-Token": self.state.token,
                   "Content-Type": "application/json"}
        with patch("twrpdtgen.git_updater.apply_update",
                   side_effect=GitUpdateError(
                       "Already up to date. Nothing new to check out.")) as updater:
            with self.assertRaises(HTTPError) as exc:
                self.request(
                    "/api/git/apply", "POST",
                    json.dumps({"confirmed": True}).encode(), headers)
            self.assertEqual(exc.exception.code, 409)
            updater.assert_called_once_with(confirmed=True)

    def test_git_update_rejected_during_generation(self):
        headers = {"X-CSRF-Token": self.state.token,
                   "Content-Type": "application/json"}
        with self.state.lock:
            self.state.status = "running"
        with self.assertRaises(HTTPError) as exc:
            self.request("/api/git/check", "POST", b"{}", headers)
        self.assertEqual(exc.exception.code, 409)

    def test_generation_returns_only_created_zip(self):
        input_file = self.state.workspace / "recovery.img"
        input_file.write_bytes(b"stock")
        bundle = self.state.workspace / "generated.zip"
        bundle.write_bytes(b"fake-zip")
        payload = json.dumps({
            "source": str(input_file),
            "output": str(self.state.workspace / "output"),
            "mode": "tree",
            "recovery_layout": "dedicated",
        }).encode()
        headers = {"X-CSRF-Token": self.state.token,
                   "Content-Type": "application/json"}
        with patch("twrpdtgen.webgui.run_job",
                   return_value=GUIResult(archive=bundle)):
            with self.request("/api/start", "POST", payload, headers) as res:
                self.assertEqual(json.load(res)["status"], "running")
            self.state.thread.join(timeout=5)
        with self.request("/api/status") as res:
            status = json.load(res)
        self.assertEqual(status["status"], "done")
        self.assertIn("download", status)
        with self.request(status["download"]) as res:
            self.assertEqual(res.read(), b"fake-zip")
            self.assertEqual(res.headers["Content-Type"], "application/zip")
        with self.assertRaises(HTTPError) as exc:
            self.request("/api/download?key=not-a-token")
        self.assertEqual(exc.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
