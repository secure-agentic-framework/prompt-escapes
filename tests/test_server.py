import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from server import load_env, make_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.server = make_server("127.0.0.1", 0, Path(cls.tmp.name) / "http.sqlite3")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def request(self, path, body=None, token=None, host=None):
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["X-Travel-Token"] = token
        if host:
            headers["Host"] = host
        req = urllib.request.Request(self.base + path,
            data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def setUp(self):
        _, self.config = self.request("/api/config")
        self.token = self.config["csrf"]

    def test_full_http_search_approval_persistence_and_cancellation(self):
        code, trip = self.request("/api/trips", {}, self.token)
        self.assertEqual(code, 201)
        path = "/api/trips/" + trip["id"]
        code, trip = self.request(path + "/search", {}, self.token)
        self.assertEqual(code, 200)
        option = trip["options"][0]
        consent = {"option_id": option["id"], "expected_total": option["total_cents"]}
        code, _ = self.request(path + "/book", consent, self.token)
        self.assertEqual(code, 400)
        consent["approved"] = True
        code, booked = self.request(path + "/book", consent, self.token)
        self.assertEqual(code, 200)
        self.assertEqual(booked["status"], "booked")
        _, reloaded = self.request(path)
        self.assertEqual(reloaded["reservations"], booked["reservations"])
        code, cancelled = self.request(path + "/cancel", {"reservation_id": booked["reservations"][0]["id"], "approved": True}, self.token)
        self.assertEqual(code, 200)
        self.assertEqual(cancelled["status"], "partial")

    def test_missing_token_and_dns_rebinding_host_rejected(self):
        code, _ = self.request("/api/trips", {})
        self.assertEqual(code, 403)
        code, _ = self.request("/api/config", host="attacker.example")
        self.assertEqual(code, 403)

    def test_config_never_returns_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-test-value"}):
            _, config = self.request("/api/config")
        self.assertTrue(config["ai_available"])
        self.assertNotIn("secret-test-value", json.dumps(config))

    def test_missing_key_is_reported_without_silent_demo_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            _, trip = self.request("/api/trips", {}, self.token)
            code, result = self.request("/api/trips/" + trip["id"] + "/chat", {"message": "Find a trip", "mode": "ai"}, self.token)
        self.assertEqual(code, 502)
        self.assertIn("OPENAI_API_KEY", result["error"])

    def test_static_page_and_security_headers(self):
        with urllib.request.urlopen(self.base, timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("Prompt Escapes", response.read().decode())
            self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_body_shape_is_checked(self):
        code, _ = self.request("/api/trips", [], self.token)
        self.assertEqual(code, 400)

    def test_challenge_launch_editor_and_http_responses_hide_private_fixtures(self):
        code, trip = self.request("/api/lab/launch", {"challenge_id": "brochure", "variant": "vulnerable"}, self.token)
        self.assertEqual(code, 201)
        self.assertNotIn("_world", trip)
        self.assertNotIn("DEMO-REWARDS-", json.dumps(trip))
        path = "/api/trips/" + trip["id"]
        code, edited = self.request(path + "/brochure", {"text": "An untrusted partner note"}, self.token)
        self.assertEqual(code, 200)
        self.assertEqual(edited["lab"]["brochure"], "An untrusted partner note")
        self.assertNotIn("_world", edited)
        _, reloaded = self.request(path)
        self.assertNotIn("DEMO-PRIVATE-", json.dumps(reloaded))
        code, _ = self.request(path + "/chat", {"message": "Look up T200", "mode": "demo"}, self.token)
        self.assertEqual(code, 400)

    def test_http_cannot_execute_model_tools_or_forge_completion(self):
        _, trip = self.request("/api/lab/launch", {"challenge_id": "traveler", "variant": "vulnerable", "solved": True}, self.token)
        self.assertFalse(trip["lab"]["solved"])
        path = "/api/trips/" + trip["id"]
        for action in ("lookup_traveler", "tool", "grade", "save_planning_note"):
            code, _ = self.request(path + "/" + action, {"traveler_id": "T200", "solved": True}, self.token)
            self.assertEqual(code, 404)
        _, trip = self.request(path)
        self.assertFalse(trip["lab"]["solved"])
        _, board = self.request("/api/lab")
        self.assertEqual(board["maximum"], 450)
        self.assertEqual(board["score"], 0)


class EnvironmentTests(unittest.TestCase):
    def test_dotenv_does_not_execute_or_override_shell_environment(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"OPENAI_API_KEY": "launch-key"}, clear=True):
            path = Path(folder) / ".env"
            path.write_text("OPENAI_API_KEY=file-key\nOPENAI_MODEL='configured-model'\nHOME=/unexpected\nIGNORED=$(echo wrong)\n")
            load_env(path)
            self.assertEqual(os.environ["OPENAI_API_KEY"], "launch-key")
            self.assertEqual(os.environ["OPENAI_MODEL"], "configured-model")
            self.assertNotIn("HOME", os.environ)
            self.assertNotIn("IGNORED", os.environ)
