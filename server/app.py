"""Original implementation. Python 3.10+, no third-party runtime dependencies.

Use behind a TLS reverse proxy for remote experiments. Client compatibility is
experimental: HTTP tests do not establish Android end-to-end compatibility.
"""
import argparse
from contextlib import contextmanager
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger("luxblox")
MAX_BODY = 65536
SESSION_COOKIE = ".ROBLOSECURITY"
CSRF_COOKIE = "LUXBLOX-CSRF"
SESSION_TTL = 86400


class ApiError(Exception):
    def __init__(self, status, message, code=0):
        self.status, self.message, self.code = status, message, code


class Backend:
    def __init__(self, database, settings, secure_cookies=True):
        self.database = str(database)
        self.settings = json.loads(Path(settings).read_text(encoding="utf-8"))
        values = self.settings.get("applicationSettings")
        if not isinstance(values, dict) or any(not isinstance(v, str) for v in values.values()):
            raise ValueError("applicationSettings must be an object of string values")
        self.secure_cookies = secure_cookies
        self.csrf_secret = secrets.token_bytes(32)
        self.rate_lock = Lock()
        self.attempts = {}
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    salt BLOB NOT NULL, password_hash BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    expires INTEGER NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def rate_limit(self, address):
        now = time.monotonic()
        with self.rate_lock:
            self.attempts = {k: v for k, v in self.attempts.items() if now - v[0] < 600}
            start, count = self.attempts.get(address, (now, 0))
            if count >= 20:
                raise ApiError(429, "Too many attempts. Try again later.")
            self.attempts[address] = (start, count + 1)

    @staticmethod
    def password_hash(password, salt):
        return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)

    def register(self, username, password):
        if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username):
            raise ApiError(400, "Username must contain 3-20 letters, digits or underscores.")
        if not 8 <= len(password) <= 128:
            raise ApiError(400, "Password must contain 8-128 characters.")
        salt = secrets.token_bytes(16)
        digest = self.password_hash(password, salt)
        try:
            with self.connect() as db:
                cur = db.execute("INSERT INTO users(username,salt,password_hash) VALUES(?,?,?)",
                                 (username, salt, digest))
                return {"id": cur.lastrowid, "name": username, "displayName": username}
        except sqlite3.IntegrityError:
            raise ApiError(409, "Username is unavailable.") from None

    def login(self, username, password):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        # Run the password KDF even for absent users.
        digest = self.password_hash(password, row["salt"] if row else bytes(16))
        if row is None or not hmac.compare_digest(digest, row["password_hash"]):
            raise ApiError(403, "Incorrect username or password.", 1)
        return {"id": row["id"], "name": row["username"], "displayName": row["username"]}

    def session(self, user_id):
        token = secrets.token_urlsafe(48)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires<=?", (int(time.time()),))
            db.execute("INSERT INTO sessions VALUES(?,?,?)",
                       (hashlib.sha256(token.encode()).hexdigest(), user_id, int(time.time()) + SESSION_TTL))
        return token

    def current_user(self, token):
        with self.connect() as db:
            row = db.execute("""SELECT users.id, users.username FROM sessions
                JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires>?""",
                (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        if row is None:
            raise ApiError(401, "Authentication required.")
        return {"id": row["id"], "name": row["username"], "displayName": row["username"]}


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, backend):
        self.backend = backend
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "LuxBlox/0.1"
    timeout = 15

    def log_message(self, *_):
        pass  # Do not log request lines: queries may contain credentials.

    def cookies(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except CookieError:
            pass
        return cookie

    def cookie_value(self, name):
        cookie = self.cookies()
        return cookie[name].value if name in cookie else ""

    def cookie_header(self, name, value, max_age):
        return (f"{name}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
                + ("; Secure" if self.server.backend.secure_cookies else ""))

    def reply(self, status, payload=None, headers=()):
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        # Deliberately exclude host, query, body, headers, cookies and device IDs.
        LOG.info(json.dumps({"method": self.command, "path": self.path_only,
                             "status": status}, ensure_ascii=True))

    def require_csrf(self):
        nonce = self.cookie_value(CSRF_COOKIE)
        token = self.headers.get("X-CSRF-TOKEN", "")
        expected = hmac.new(self.server.backend.csrf_secret, nonce.encode(), "sha256").hexdigest()
        if nonce and hmac.compare_digest(token, expected):
            return True
        nonce = secrets.token_urlsafe(24)
        expected = hmac.new(self.server.backend.csrf_secret, nonce.encode(), "sha256").hexdigest()
        self.reply(403, {"errors": [{"code": 0, "message": "Token Validation Failed"}]},
                   [("X-CSRF-TOKEN", expected),
                    ("Set-Cookie", self.cookie_header(CSRF_COOKIE, nonce, SESSION_TTL))])
        return False

    def read_json(self):
        if self.headers.get("Transfer-Encoding"):
            raise ApiError(400, "Transfer-Encoding is not supported.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError(400, "Invalid Content-Length.") from None
        if length < 0 or length > MAX_BODY:
            raise ApiError(413, "Request is too large.")
        if self.headers.get_content_type() != "application/json":
            raise ApiError(415, "Use application/json.")
        try:
            data = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "Invalid JSON.") from None
        if not isinstance(data, dict):
            raise ApiError(400, "Expected a JSON object.")
        return data

    def do_GET(self):
        self.handle_api()

    def do_POST(self):
        self.handle_api()

    def do_HEAD(self):
        self.handle_api()

    def handle_api(self):
        url = urlsplit(self.path)
        self.path_only = url.path[:512]
        self.close_connection = True
        try:
            self.route(url)
        except ApiError as exc:
            self.reply(exc.status, {"errors": [{"code": exc.code, "message": exc.message}]})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            LOG.error("Internal request failure (%s)", self.path_only)
            self.reply(500, {"errors": [{"code": 0, "message": "Internal server error."}]})

    def route(self, url):
        path = url.path.rstrip("/") or "/"
        backend = self.server.backend
        if path in ("/", "/healthz") and self.command in ("GET", "HEAD"):
            return self.reply(200, {"service": "LuxBlox", "stage": "experimental-bootstrap", "ok": True})
        if path in ("/v1/settings/application", "/v2/settings/application") and self.command in ("GET", "POST", "HEAD"):
            query = parse_qs(url.query)
            name = query.get("applicationName", [""])[0]
            if name != "AndroidApp":
                raise ApiError(400, "Only applicationName=AndroidApp is supported.")
            return self.reply(200, backend.settings)
        if path in ("/mobile/pbe", "/client/pbe") and self.command in ("GET", "POST", "HEAD"):
            return self.reply(200)
        if path == "/device/initialize" and self.command in ("GET", "POST", "HEAD"):
            # Opaque per-response ID for this experiment; no device fingerprint is stored.
            return self.reply(200, {"browserTrackerId": secrets.randbelow(2**52) + 1,
                                    "appDeviceIdentifier": None})
        if path in ("/mobileapi/check-app-version", "/v1/mobile-client-version") and self.command in ("GET", "POST", "HEAD"):
            return self.reply(200, {"data": {"UpgradeAction": "None"}})
        if path == "/v1/enrollments" and self.command in ("GET", "POST", "HEAD"):
            return self.reply(200, {"data": []})
        if path == "/v1/get-enrollments" and self.command in ("GET", "POST", "HEAD"):
            return self.reply(200, [])
        if path == "/v1.1/Counters/Increment" and self.command in ("GET", "POST", "HEAD"):
            return self.reply(200)
        if path == "/v1/users/authenticated" and self.command in ("GET", "HEAD"):
            return self.reply(200, backend.current_user(self.cookie_value(SESSION_COOKIE)))
        if path in ("/v1/login", "/v2/login", "/v2/signup", "/v2/logout") and self.command == "POST":
            if not self.require_csrf():
                return
            if path == "/v2/logout":
                token = self.cookie_value(SESSION_COOKIE)
                with backend.connect() as db:
                    db.execute("DELETE FROM sessions WHERE token_hash=?",
                               (hashlib.sha256(token.encode()).hexdigest(),))
                return self.reply(200, {}, [("Set-Cookie", self.cookie_header(SESSION_COOKIE, "", 0))])
            backend.rate_limit(self.client_address[0])
            body = self.read_json()
            username = body.get("username", body.get("cvalue", ""))
            password = body.get("password", "")
            if not isinstance(username, str) or not isinstance(password, str) or len(username) > 128 or len(password) > 128:
                raise ApiError(400, "Invalid credentials format.")
            if path == "/v2/signup":
                user = backend.register(username, password)
            else:
                if body.get("ctype", "Username") != "Username":
                    raise ApiError(400, "Only username login is supported.")
                user = backend.login(username, password)
            token = backend.session(user["id"])
            return self.reply(200, {"userId": user["id"], "user": user, "isBanned": False},
                              [("Set-Cookie", self.cookie_header(SESSION_COOKIE, token, SESSION_TTL))])
        # Unknown requests must stay visible. Never report false success for them.
        raise ApiError(404, "This endpoint has not been implemented in LuxBlox.")


def main():
    parser = argparse.ArgumentParser(description="LuxBlox compatibility experiment")
    parser.add_argument("--host", default=os.getenv("LUXBLOX_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")))
    parser.add_argument("--database", default=os.getenv("LUXBLOX_DATABASE", "data/luxblox.sqlite3"))
    parser.add_argument("--settings", default=str(ROOT / "config/AndroidApp.json"))
    parser.add_argument("--insecure-local-cookies", action="store_true")
    args = parser.parse_args()
    if args.insecure_local_cookies and args.host not in ("127.0.0.1", "::1", "localhost"):
        parser.error("Insecure cookies are allowed only with a loopback listener")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    backend = Backend(args.database, args.settings, not args.insecure_local_cookies)
    server = Server((args.host, args.port), backend)
    LOG.info("LuxBlox listening on %s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
