"""Shared localhost-only HTTP kit for the DupeHunter / SpeedLog / QuickFind apps (same pattern as
PulseScope and LanScope): 127.0.0.1 only, Host-header check, random per-launch token on every POST,
strict CSP, realpath+commonpath static files, JSON bodies only, no print()."""
import json
import mimetypes
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HOST = "127.0.0.1"
MAX_BODY = 256 * 1024
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json"}
TOKEN_PLACEHOLDER = b"__APP_TOKEN__"


class BadRequest(Exception):
    pass


class NotFound(Exception):
    pass


class Kit:
    def __init__(self, name, port_env, default_port, base_dir=None):
        self.name = name
        self.port = int(os.environ.get(port_env, str(default_port)))
        base = base_dir or getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        self.web_dir = os.path.realpath(os.path.join(base, "web"))
        self.token = secrets.token_urlsafe(24)
        self.get_routes = {}
        self.post_routes = {}
        self.raw_routes = {}      # GET routes that return (status, body, ctype, headers)
        self._last_seen = time.time()
        self.lock = threading.Lock()

    # registration
    def get(self, path):
        def deco(fn):
            self.get_routes[path] = fn
            return fn
        return deco

    def post(self, path):
        def deco(fn):
            self.post_routes[path] = fn
            return fn
        return deco

    def raw(self, path):
        def deco(fn):
            self.raw_routes[path] = fn
            return fn
        return deco

    def last_seen(self):
        return self._last_seen

    def touch(self):
        self._last_seen = time.time()

    def build_server(self, port=None):
        kit = self

        class Handler(BaseHTTPRequestHandler):
            server_version = kit.name
            sys_version = ""

            def log_message(self, *args):
                pass

            def _send(self, status, body, ctype, extra=None):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "Content-Security-Policy": CSP}
                headers.update(extra or {})
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def send_json(self, obj, status=200):
                self._send(status, json.dumps(obj, allow_nan=False, default=str).encode("utf-8"), "application/json")

            def _guard(self):
                host = (self.headers.get("Host") or "").lower()
                p = self.server.server_address[1]
                if host not in (f"127.0.0.1:{p}", f"localhost:{p}"):
                    self.send_json({"error": "forbidden host"}, 403)
                    return False
                return True

            def do_GET(self):
                if not self._guard():
                    return
                parts = urlsplit(self.path)
                path = parts.path
                if path.startswith("/api/"):
                    kit.touch()
                    q = {k: v[-1] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
                    try:
                        if path in kit.raw_routes:
                            status, body, ctype, headers = kit.raw_routes[path](q)
                            return self._send(status, body, ctype, headers)
                        fn = kit.get_routes.get(path)
                        if fn is None:
                            return self.send_json({"error": "not found"}, 404)
                        return self.send_json(fn(q))
                    except BadRequest as e:
                        return self.send_json({"error": str(e)}, 400)
                    except NotFound as e:
                        return self.send_json({"error": str(e)}, 404)
                    except Exception as e:  # noqa: BLE001
                        return self.send_json({"error": str(e)}, 500)
                self._static(path)

            do_HEAD = do_GET

            def do_POST(self):
                if not self._guard():
                    return
                fn = kit.post_routes.get(urlsplit(self.path).path)
                if fn is None:
                    return self.send_json({"error": "not found"}, 404)
                if not secrets.compare_digest(self.headers.get("X-App-Token") or "", kit.token):
                    return self.send_json({"error": "invalid token"}, 403)
                if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
                    return self.send_json({"error": "Content-Type must be application/json"}, 415)
                try:
                    length = int(self.headers.get("Content-Length") or "0")
                except ValueError:
                    return self.send_json({"error": "bad Content-Length"}, 400)
                if length < 0 or length > MAX_BODY:
                    return self.send_json({"error": "body too large"}, 413)
                try:
                    data = json.loads(self.rfile.read(length) or b"{}")
                except (ValueError, UnicodeDecodeError):
                    return self.send_json({"error": "invalid JSON"}, 400)
                if not isinstance(data, dict):
                    return self.send_json({"error": "JSON body must be an object"}, 400)
                kit.touch()
                try:
                    self.send_json(fn(data))
                except BadRequest as e:
                    self.send_json({"error": str(e)}, 400)
                except NotFound as e:
                    self.send_json({"error": str(e)}, 404)
                except Exception as e:  # noqa: BLE001
                    self.send_json({"error": str(e)}, 500)

            def _static(self, path):
                if path in ("", "/"):
                    path = "/index.html"
                full = os.path.realpath(os.path.join(kit.web_dir, path.lstrip("/").replace("/", os.sep)))
                try:
                    inside = os.path.commonpath([full, kit.web_dir]) == kit.web_dir
                except ValueError:       # different drives on Windows
                    inside = False
                if not inside or not os.path.isfile(full):
                    return self.send_json({"error": "not found"}, 404)
                ext = os.path.splitext(full)[1].lower()
                with open(full, "rb") as f:
                    body = f.read()
                if ext == ".html":
                    body = body.replace(TOKEN_PLACEHOLDER, kit.token.encode("ascii"))
                self._send(200, body, TYPES.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream")

        class QuietServer(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
                    return          # the page cancelled a search it no longer needs
                super().handle_error(request, client_address)

        httpd = QuietServer((HOST, port or self.port), Handler)
        httpd.daemon_threads = True
        return httpd
