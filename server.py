#!/usr/bin/env python3
"""Run with python3 server.py. No external dependencies required."""

import argparse
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from travel.agent import Agent, AgentError
from travel.simulator import CITIES, SCENARIOS, RuleError, Store

ROOT = Path(__file__).resolve().parent


def load_env(path):
    """Read simple KEY=value lines without executing shell code or overriding env."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip()
        if key in ("OPENAI_API_KEY", "OPENAI_MODEL"):
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key, value)


def make_server(host, port, db_path):
    store = Store(db_path)
    agent = Agent(store)
    csrf = secrets.token_urlsafe(32)
    locks = {}
    locks_guard = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Request bodies, model messages, and keys are never logged.
            pass

        def send(self, code, body, content_type="application/json; charset=utf-8"):
            payload = json.dumps(body).encode() if content_type.startswith("application/json") else body
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def valid_host(self):
            return self.headers.get("Host", "") in ("127.0.0.1:" + str(self.server.server_port), "localhost:" + str(self.server.server_port))

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {"error": "Localhost access only."})
            path = urlparse(self.path).path
            try:
                if path == "/api/config":
                    return self.send(200, {"ai_available": bool(os.environ.get("OPENAI_API_KEY")),
                        "model": os.environ.get("OPENAI_MODEL", "gpt-6.1-sol"), "csrf": csrf,
                        "cities": CITIES, "scenarios": SCENARIOS})
                if path.startswith("/api/trips/"):
                    return self.send(200, store.get(path.split("/")[-1]))
                files = {"/": ("index.html", "text/html; charset=utf-8"),
                         "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                         "/styles.css": ("styles.css", "text/css; charset=utf-8")}
                if path in files:
                    name, mime = files[path]
                    return self.send(200, (ROOT / "static" / name).read_bytes(), mime)
                return self.send(404, {"error": "Not found."})
            except RuleError as exc:
                return self.send(404, {"error": str(exc)})

        def do_POST(self):
            if not self.valid_host() or not secrets.compare_digest(self.headers.get("X-Travel-Token", ""), csrf):
                return self.send(403, {"error": "Refresh the local app before making changes."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    return self.send(413, {"error": "Request is too large or empty."})
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self.send(415, {"error": "Use application/json."})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise RuleError("Request must be a JSON object.")
                parts = urlparse(self.path).path.strip("/").split("/")
                if parts == ["api", "trips"]:
                    return self.send(201, store.create(body.get("scenario", "normal")))
                if len(parts) != 4 or parts[:2] != ["api", "trips"]:
                    return self.send(404, {"error": "Not found."})
                trip_id, action = parts[2:]
                with locks_guard:
                    lock = locks.setdefault(trip_id, threading.Lock())
                with lock:
                    if action == "profile":
                        state = store.update(trip_id, body)
                    elif action == "search":
                        state = store.search(trip_id)
                    elif action == "chat":
                        state = agent.respond(trip_id, body.get("message"), body.get("mode", "demo"))
                    elif action == "book":
                        if body.get("approved") is not True:
                            raise RuleError("Explicit approval is required before booking.")
                        state = store.book(trip_id, body.get("option_id"), body.get("expected_total"))
                    elif action == "cancel":
                        if body.get("approved") is not True:
                            raise RuleError("Explicit cancellation is required.")
                        state = store.cancel(trip_id, body.get("reservation_id"))
                    else:
                        return self.send(404, {"error": "Unknown action."})
                return self.send(200, state)
            except (RuleError, ValueError, TypeError, KeyError) as exc:
                return self.send(400, {"error": str(exc)})
            except AgentError as exc:
                return self.send(502, {"error": str(exc)})
            except Exception:
                return self.send(500, {"error": "The request failed. Reload the saved trip before retrying."})

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


if __name__ == "__main__":
    load_env(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Local fictional travel agent")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "travel.sqlite3")
    args = parser.parse_args()
    server = make_server("127.0.0.1", args.port, args.db)
    print("Wayfarer is running at http://127.0.0.1:{}".format(server.server_port), flush=True)
    print("AI mode: " + ("enabled" if os.environ.get("OPENAI_API_KEY") else "key not visible; scripted demo available"), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
