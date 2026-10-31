"""Original implementation. Python 3.10+. PostgreSQL mode uses Psycopg 3; local SQLite stays available.

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
from server import realtime, postgres, accounts, account_pages, chat, features, feature_routes, native_routes
from server.errors import ApiError

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger("luxblox")
MAX_BODY = 65536
SESSION_COOKIE = ".ROBLOSECURITY"
CSRF_COOKIE = "LUXBLOX-CSRF"
SESSION_TTL = 86400


class Backend:
    def __init__(self, database, settings, secure_cookies=True, database_url=None):
        self.owner_user_id = int(os.getenv("LUXBLOX_OWNER_USER_ID", "2"))
        self.public_origin = os.getenv("LUXBLOX_PUBLIC_ORIGIN", "https://luxblox-api.onrender.com").rstrip("/")
        if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]+)?", self.public_origin):
            raise ValueError("LUXBLOX_PUBLIC_ORIGIN must be an HTTPS origin")
        self.database = str(database)
        self.database_url = database_url
        self.is_postgres = bool(database_url)
        self.pool = postgres.create_pool(database_url) if self.is_postgres else None
        self.integrity_errors = (sqlite3.IntegrityError,)
        if self.is_postgres:
            import psycopg
            self.integrity_errors = (psycopg.errors.UniqueViolation,)
        self.settings = json.loads(Path(settings).read_text(encoding="utf-8"))
        self.app_policy = json.loads((ROOT / "config/app-policy.json").read_text(encoding="utf-8"))
        values = self.settings.get("applicationSettings")
        if not isinstance(values, dict) or any(not isinstance(v, str) for v in values.values()):
            raise ValueError("applicationSettings must be an object of string values")
        self.secure_cookies = secure_cookies
        self.csrf_secret = secrets.token_bytes(32)
        self.realtime_secret = secrets.token_bytes(32)
        self.rate_lock = Lock()
        self.attempts = {}
        self.chat_attempts = {}
        if not self.is_postgres:
            Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            if self.is_postgres:
                postgres.initialize(db)
            else:
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
            accounts.initialize(db, self.is_postgres)
            chat.initialize(db, self.is_postgres)
            features.initialize(db)

    @contextmanager
    def connect(self):
        if self.is_postgres:
            with self.pool.connection() as connection:
                connection.execute("SET LOCAL statement_timeout = '10s'")
                yield postgres.Connection(connection)
            return
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def close(self):
        if self.pool is not None:self.pool.close()

    def rate_limit(self, address):
        now = time.monotonic()
        with self.rate_lock:
            self.attempts = {k: v for k, v in self.attempts.items() if now - v[0] < 600}
            start, count = self.attempts.get(address, (now, 0))
            if count >= 20:
                raise ApiError(429, "Too many attempts. Try again later.")
            self.attempts[address] = (start, count + 1)

    def rate_limit_chat(self, user_id):
        now = time.monotonic()
        with self.rate_lock:
            self.chat_attempts = {k:v for k,v in self.chat_attempts.items() if now-v[0]<60}
            start, count = self.chat_attempts.get(user_id, (now,0))
            if count >= 60:
                raise ApiError(429, "Слишком много сообщений. Подождите минуту.")
            self.chat_attempts[user_id] = (start,count+1)

    @staticmethod
    def password_hash(password, salt):
        return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)

    def validate_username(self, username):
        if not isinstance(username, str) or not username:
            return 9, "Введите никнейм."
        if not 3 <= len(username) <= 20:
            return 3, "Нужно от 3 до 20 символов."
        if " " in username:
            return 6, "Никнейм не должен содержать пробелы."
        if not re.fullmatch(r"[A-Za-z0-9_]+", username):
            return 7, "Используйте латинские буквы, цифры и подчёркивание."
        if username.startswith("_") or username.endswith("_"):
            return 4, "Подчёркивание не может быть первым или последним символом."
        if username.count("_") > 1:
            return 5, "Допустимо не больше одного подчёркивания."
        with self.connect() as db:
            exists = db.execute("SELECT 1 FROM users WHERE lower(username)=lower(?)", (username,)).fetchone()
        if exists:
            return 1, "Этот никнейм уже занят."
        return 0, ""

    @staticmethod
    def validate_password(username, password):
        if not isinstance(password, str) or not 8 <= len(password) <= 128:
            return 2, "Пароль должен содержать от 8 до 128 символов."
        if username and password.casefold() == username.casefold():
            return 3, "Пароль должен отличаться от никнейма."
        return 0, ""

    def register(self, username, password):
        code, message = self.validate_username(username)
        if code:
            raise ApiError(409 if code == 1 else 400, message, code)
        code, message = self.validate_password(username, password)
        if code:
            raise ApiError(400, message, code)
        salt = secrets.token_bytes(16)
        digest = self.password_hash(password, salt)
        try:
            with self.connect() as db:
                query = "INSERT INTO users(username,salt,password_hash) VALUES(?,?,?)"
                if self.is_postgres:
                    query += " RETURNING id"
                cur = db.execute(query, (username, salt, digest))
                user_id = cur.fetchone()["id"] if self.is_postgres else cur.lastrowid
                return {"id": user_id, "name": username, "displayName": username}
        except self.integrity_errors:
            raise ApiError(409, "Username is unavailable.") from None

    def login(self, username, password):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE lower(username)=lower(?)", (username,)).fetchone()
        # Run the password KDF even for absent users.
        digest = self.password_hash(password, row["salt"] if row else bytes(16))
        if row is None or not hmac.compare_digest(digest, row["password_hash"]):
            raise ApiError(403, "Incorrect username or password.", 1)
        return {"id": row["id"], "name": row["username"],
                "displayName": accounts.profile(self, row["id"])["displayName"]}

    def session(self, user_id):
        token = secrets.token_urlsafe(48)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires<=?", (int(time.time()),))
            db.execute("INSERT INTO sessions VALUES(?,?,?)",
                       (hashlib.sha256(token.encode()).hexdigest(), user_id, int(time.time()) + SESSION_TTL))
        return token

    def current_account(self, token):
        with self.connect() as db:
            row = db.execute("""SELECT users.id, users.username, account_profiles.display_name,
                COALESCE(account_profiles.robux,0) AS robux FROM sessions
                JOIN users ON users.id=sessions.user_id
                LEFT JOIN account_profiles ON account_profiles.user_id=users.id
                WHERE token_hash=? AND expires>?""",
                (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        if row is None:
            raise ApiError(401, "Authentication required.")
        return {"id": row["id"], "name": row["username"], "username": row["username"],
                "displayName": row["display_name"] or row["username"], "robux": row["robux"], **features.flags(self,row["id"])}

    def current_user(self, token):
        profile = self.current_account(token)
        return {k: profile[k] for k in ("id", "name", "displayName")}


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
        body = (payload if isinstance(payload, bytes) else
                b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode())
        self.send_response(status)
        self.send_header("Content-Type", next((v for k, v in headers if k.lower() == "content-type"),
                                             "application/json; charset=utf-8"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in headers:
            if name.lower() != "content-type":
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

    def do_PATCH(self):
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
        path = re.sub(r"/+", "/", url.path).rstrip("/") or "/"
        # Lua service names are path namespaces on our single Render origin.
        # Keep Java's classic /users/account-info and /realtime/... unchanged.
        namespace, _, tail = path.lstrip("/").partition("/")
        services = {"api", "apis", "auth", "accountsettings", "avatar", "catalog",
                    "inventory", "assetdelivery", "chat", "friends", "users", "assetgame", "games",
                    "groups", "notifications", "presence", "web", "www", "ads",
                    "followings", "economy", "thumbnails", "premiumfeatures", "locale",
                    "badges", "metrics", "apis.rcs", "discussions", "contacts", "search", "static"}
        if namespace in services and (tail.startswith(("v1/", "v1.1/", "v1.0/", "v2/", "v3/"))
                                      or namespace in {"api", "apis", "web", "www", "assetgame"}):
            path = "/" + tail
        backend = self.server.backend
        # R9 LuaApp: POST /presence/v1/presence/users. Friend loading waits
        # for this request to resolve before dispatching FetchUserFriendsCompleted.
        if namespace == "presence" and path == "/v1/presence/users" and self.command == "POST":
            backend.current_user(self.cookie_value(SESSION_COOKIE))
            body = self.read_json()
            ids = body.get("userIds")
            if not isinstance(ids, list) or len(ids) > 100 or any(type(i) is not int or i <= 0 for i in ids):
                raise ApiError(400, "Invalid userIds.")
            return self.reply(200, {"userPresences": [
                {"userId": i, "userPresenceType": 0, "lastLocation": "",
                 "placeId": None, "rootPlaceId": None, "gameId": None,
                 "universeId": None, "lastOnline": None}
                for i in ids
            ]})
        if native_routes.route(self,path,url,namespace):
            return
        if feature_routes.route(self, path, url, namespace):
            return
        # The 2021 LuaApp uses chat.roblox.com/v2-style routes. Domain rewriting
        # places them under /chat/v2 on Render; serve account-scoped data here.
        if path == "/v2/chat-settings" and self.command in ("GET", "HEAD"):
            backend.current_user(self.cookie_value(SESSION_COOKIE))
            return self.reply(200, {"isActiveChatUser": True, "isConnectTabEnabled": False,
                                    "isChatEnabled": True, "isActive": True})
        if path in ("/v2/get-user-conversations", "/v2/get-conversations") and self.command in ("GET", "HEAD"):
            user = backend.current_user(self.cookie_value(SESSION_COOKIE))
            query = parse_qs(url.query)
            try:
                page = int(query.get("pageNumber", ["1"])[0])
                size = int(query.get("pageSize", ["20"])[0])
            except ValueError:
                raise ApiError(400, "Некорректная страница чатов.") from None
            return self.reply(200, chat.conversations(backend, user["id"], page, size))
        if path in ("/v2/get-conversation-messages", "/v2/get-messages") and self.command in ("GET", "HEAD"):
            user = backend.current_user(self.cookie_value(SESSION_COOKIE))
            query = parse_qs(url.query)
            try:
                conversation_id = query.get("conversationId", [""])[0]
                page = int(query.get("pageNumber", ["1"])[0])
                size = int(query.get("pageSize", ["50"])[0])
            except ValueError:
                raise ApiError(400, "Некорректный запрос сообщений.") from None
            return self.reply(200, chat.conversation_messages(
                backend, conversation_id, user["id"], page, size))
        if path == "/v2/get-unread-conversation-count" and self.command in ("GET", "HEAD"):
            backend.current_user(self.cookie_value(SESSION_COOKIE))
            return self.reply(200, {"count": 0})
        if path == "/v2/start-one-to-one-conversation" and self.command == "POST":
            user = backend.current_user(self.cookie_value(SESSION_COOKIE))
            if not self.require_csrf():
                return
            body = self.read_json()
            participant = body.get("participantuserId", body.get("participantUserId"))
            conversation=chat.start_conversation(backend, user["id"], participant)
            return self.reply(200, {**conversation,'resultType':'Success','conversation':conversation})
        if path in ("/v2/send-message", "/v2/send-game-link-message") and self.command == "POST":
            user = backend.current_user(self.cookie_value(SESSION_COOKIE))
            if not self.require_csrf():
                return
            backend.rate_limit_chat(user["id"])
            body = self.read_json()
            text = body.get("message")
            if path.endswith("send-game-link-message"):
                text = "Приглашение в игру"
            message_id = chat.send_to_conversation(
                backend, body.get("conversationId"), user["id"], text)
            from datetime import datetime,timezone
            return self.reply(200, {"messageId": message_id, "id": message_id,
                'conversationId':int(body['conversationId']), 'senderTargetId':user['id'],
                'content':text, 'filteredForReceivers':False, 'messageType':'PlainText',
                'sent':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'), 'resultType':'Success'})
        if path == "/luxblox/chat/messages" and self.command in ("GET", "HEAD"):
            user = backend.current_user(self.cookie_value(SESSION_COOKIE))
            return self.reply(200, {"data": chat.messages(backend, user["id"])})
        if path == "/luxblox/chat/send" and self.command == "POST":
            user = backend.current_user(self.cookie_value(SESSION_COOKIE))
            if not self.require_csrf():
                return
            backend.rate_limit_chat(user["id"])
            body = self.read_json()
            message_id = chat.send(backend, user["id"], body.get("recipient"), body.get("message"))
            return self.reply(200, {"id": message_id})
        if path in ("/my/messages", "/messages") and self.command in ("GET", "POST", "HEAD"):
            session = self.cookie_value(SESSION_COOKIE)
            user = backend.current_user(session)
            csrf = accounts.token(backend, user["id"], session)
            status, message = 200, ""
            if self.command == "POST":
                try:
                    if self.headers.get_content_type() != "application/x-www-form-urlencoded" or self.headers.get("Transfer-Encoding"):
                        raise ApiError(415, "Отправьте сообщение через форму.")
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if not 0 < length <= MAX_BODY:
                            raise ValueError()
                        values = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True, max_num_fields=8)
                        if any(len(v) != 1 for v in values.values()):
                            raise ValueError()
                        form = {k:v[0] for k,v in values.items()}
                    except (ValueError, UnicodeDecodeError):
                        raise ApiError(400, "Некорректная форма.") from None
                    if not re.fullmatch(r"[a-f0-9]{64}", form.get("csrf", "")) or not hmac.compare_digest(form["csrf"], csrf):
                        raise ApiError(403, "Откройте страницу заново и повторите.")
                    backend.rate_limit_chat(user["id"])
                    chat.send(backend, user["id"], form.get("recipient"), form.get("message"))
                    return self.reply(303, headers=[("Location", "/my/messages")])
                except ApiError as exc:
                    status, message = exc.status, exc.message
            return self.reply(status, chat.render(csrf, message, status != 200), [("Content-Type", "text/html; charset=utf-8"),
                ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")])
        if path in ("/help", "/info/about", "/about", "/info/privacy", "/info/terms-of-service") and self.command in ("GET", "HEAD"):
            page = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LuxBlox</title><body style="font:18px Arial;padding:24px"><h1>LuxBlox</h1><p>Vortix studio · 2010</p><p>Архивный игровой проект LuxBlox. Разделы сервиса находятся на нашем сервере.</p><p>Аккаунты, тестовый баланс и переписка сохраняются в базе LuxBlox.</p><p><a href="/more">Ещё: настройки и разделы LuxBlox</a></p></body></html>'
            return self.reply(200, page.encode(), [("Content-Type", "text/html; charset=utf-8")])
        if self.command in ("GET", "HEAD") and re.fullmatch(r"/static/(?:avatar-default|place-1001)\.png", path):
            asset = ROOT / "server" / "static" / path.rsplit("/", 1)[-1]
            try:
                payload = asset.read_bytes()
            except OSError:
                raise ApiError(404, "Image not found.") from None
            return self.reply(200, payload, [("Content-Type", "image/png"),
                                              ("Cache-Control", "public, max-age=86400")])
        if path in ("/upgrades/robux", "/my/account") and self.command in ("GET", "POST", "HEAD"):
            session = self.cookie_value(SESSION_COOKIE)
            profile = backend.current_account(session)
            csrf = accounts.token(backend, profile["id"], session)
            page = "robux" if path == "/upgrades/robux" else "account"
            message, status = "", 200
            if self.command == "POST":
                try:
                    if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                        raise ApiError(415, "Отправьте форму со страницы аккаунта.")
                    if self.headers.get("Transfer-Encoding"):
                        raise ApiError(400, "Некорректный запрос.")
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if not 0 < length <= MAX_BODY:
                            raise ValueError()
                        values = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True, max_num_fields=16)
                        if any(len(v) != 1 for v in values.values()):
                            raise ValueError()
                        form = {k: v[0] for k, v in values.items()}
                    except (ValueError, UnicodeDecodeError):
                        raise ApiError(400, "Некорректная форма.") from None
                    if not re.fullmatch(r"[a-f0-9]{64}", form.get("csrf", "")) or not hmac.compare_digest(form.get("csrf", ""), csrf):
                        raise ApiError(403, "Страница устарела. Откройте её заново и повторите.")
                    allowed = {"grant"} if page == "robux" else {"display_name", "username", "password"}
                    if form.get("action") not in allowed:
                        raise ApiError(400, "Операция недоступна на этой странице.")
                    backend.rate_limit(self.client_address[0])
                    accounts.mutate(backend, profile["id"], session, form)
                    return self.reply(303, headers=[("Location", path + "?saved=1")])
                except ApiError as exc:
                    status, message = exc.status, exc.message
            elif parse_qs(url.query).get("saved") == ["1"]:
                message = "Изменения сохранены."
            return self.reply(status, account_pages.render(profile, csrf, page, message, status != 200),
                              [("Content-Type", "text/html; charset=utf-8"),
                               ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"),
                               ("Referrer-Policy", "no-referrer")])
        if self.command in ("GET", "HEAD") and (namespace == "games" or namespace=='v1' and path.startswith('/v1/games')):
            catalog = json.loads((ROOT / "places/catalog.json").read_text())["experiences"]
            query = parse_qs(url.query)
            def selected(key, field):
                ids = set(",".join(query.get(key, [])).split(","))
                return [g for g in catalog if str(g[field]) in ids]
            if path == "/v1/games/multiget-place-details":
                return self.reply(200, [{
                    "placeId": g["rootPlaceId"], "name": g["name"],
                    "description": g["description"], "url": "", "builder": g["creator"]["name"],
                    "builderId": g["creator"]["id"], "isPlayable": False,
                    "reasonProhibited": "GameServerNotConfigured", "universeId": g["universeId"],
                    "universeRootPlaceId": g["rootPlaceId"], "price": 0, "imageToken": ""
                } for g in selected("placeIds", "rootPlaceId")])
            if path == "/v1/games":
                return self.reply(200, {"data": [{
                    "id": g["universeId"], "rootPlaceId": g["rootPlaceId"],
                    "name": g["name"], "description": g["description"], "creator": g["creator"],
                    "playing": 0, "visits": 0, "maxPlayers": g["maxPlayers"],
                    "price": None, "allowedGearGenres": [], "allowedGearCategories": [],
                    "isGenreEnforced": False, "copyingAllowed": False,
                    "created": "2026-10-29T00:00:00Z", "updated": "2026-10-29T00:00:00Z",
                    "studioAccessToApisAllowed": False, "universeAvatarType": "MorphToR6", "genre": "All"
                } for g in selected("universeIds", "universeId")]})
            if path == "/v1/games/sorts":
                return self.reply(200, {"sorts": [{"token": "luxblox", "name": "LuxBlox", "displayName": "LuxBlox", "gameSetTypeId": 1, "gameSetTargetId": 1001, "timeOptionsAvailable": False, "genreOptionsAvailable": False, "numberOfRows": 1, "numberOfGames": 1, "isDefaultSort": True, "tokenExpiryInSeconds": 86400}], "timeFilters": [], "genreFilters": []})
            if path == "/v1/games/list":
                return self.reply(200, {"games": [{"universeId": g["universeId"],
                    "placeId": g["rootPlaceId"], "name": g["name"], "playerCount": 0,
                    "imageToken":"luxblox-1001", "creatorType":"User", "price":0,
                    "totalUpVotes": features.votes(backend,g["universeId"])["upVotes"], "totalDownVotes": features.votes(backend,g["universeId"])["downVotes"], "isPlayable": False,
                    "creatorName": g["creator"]["name"], "creatorId": g["creator"]["id"]
                } for g in catalog], "nextPageCursor": None})
        if self.command in ("GET", "HEAD") and namespace == "thumbnails" and path == "/v1/games/icons":
            query = parse_qs(url.query)
            ids = set(",".join(query.get("universeIds", [])).split(","))
            catalog = json.loads((ROOT / "places/catalog.json").read_text())["experiences"]
            return self.reply(200, {"data": [{"targetId": g["universeId"], "state": "Completed",
                "imageUrl": f"{backend.public_origin}/static/place-{g['rootPlaceId']}.png"}
                for g in catalog if str(g["universeId"]) in ids]})
        if self.command in ("GET", "HEAD") and namespace == "thumbnails" and path == "/v1/users/avatar":
            query = parse_qs(url.query)
            ids = set(",".join(query.get("userIds", [])).split(","))
            with backend.connect() as db:
                rows = db.execute("SELECT id FROM users").fetchall()
            return self.reply(200, {"data": [{"targetId": row["id"], "state": "Completed",
                "imageUrl": features.avatar_url(backend,row["id"])}
                for row in rows if str(row["id"]) in ids]})
        if path in ("/", "/healthz") and self.command in ("GET", "HEAD"):
            return self.reply(200, {"service": "LuxBlox", "stage": "experimental-bootstrap", "ok": True})
        if path == "/universal-app-configuration/v1/behaviors/app-policy/content" and self.command in ("GET", "HEAD"):
            return self.reply(200, backend.app_policy)
        if path == "/universal-app-configuration/v1/behaviors/app-patch/content" and self.command in ("GET", "HEAD"):
            # A valid configuration with no patch rollout, not a missing response.
            return self.reply(200, {"SchemeVersion": "1", "CanaryUserIds": [], "CanaryPercentage": 0})
        if path in ("/v1/settings/application", "/v2/settings/application") and self.command in ("GET", "POST", "HEAD"):
            query = parse_qs(url.query)
            name = query.get("applicationName", [""])[0]
            if name != "AndroidApp":
                raise ApiError(400, "Only applicationName=AndroidApp is supported.")
            return self.reply(200, backend.settings)
        if path in ("/signup/is-username-valid", "/signup/is-password-valid") and self.command in ("GET", "HEAD"):
            query = parse_qs(url.query, keep_blank_values=True)
            username = query.get("username", [""])[0]
            if path.endswith("is-username-valid"):
                code, message = backend.validate_username(username)
            else:
                code, message = backend.validate_password(username, query.get("password", [""])[0])
            return self.reply(200, {"IsValid": code == 0, "ErrorCode": code, "ErrorMessage": message})
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
        if self.command in ("GET", "HEAD") and re.fullmatch(r"/v1/users/\d+", path):
            user_id = int(path.rsplit("/", 1)[1])
            with backend.connect() as db:
                row = db.execute("""SELECT users.id, users.username, account_profiles.display_name
                        FROM users LEFT JOIN account_profiles ON account_profiles.user_id=users.id
                        WHERE users.id=?""", (user_id,)).fetchone()
            if row is None:
                raise ApiError(404, "User not found.")
            return self.reply(200, {"id": row["id"], "name": row["username"],
                                    "displayName": row["display_name"] or row["username"], "description": "", "isBanned": False})
        if self.command in ("GET", "HEAD") and re.fullmatch(r"/users/\d+/profile", path):
            user_id = int(path.split("/")[2])
            with backend.connect() as db:
                row = db.execute("""SELECT users.id,users.username,account_profiles.display_name
                    FROM users LEFT JOIN account_profiles ON account_profiles.user_id=users.id
                    WHERE users.id=?""", (user_id,)).fetchone()
            if row is None:
                raise ApiError(404, "User not found.")
            return self.reply(200, {"UserId": row["id"], "Username": row["username"],
                "DisplayName": row["display_name"] or row["username"],
                "AvatarUri": features.avatar_url(backend,user_id),
                "AvatarFinal": True, "IsOnline": False, "IsBanned": False, **features.flags(backend,user_id)})
        if self.command in ("GET", "HEAD") and re.fullmatch(r"/v1/users/\d+/(friends|followers|followings)/count", path):
            return self.reply(200, {"count": 0})
        if self.command in ("GET", "HEAD") and re.fullmatch(r"/v1/users/\d+/(friends|followers|followings)", path):
            return self.reply(200, {"data": [], "previousPageCursor": None, "nextPageCursor": None})
        avatar_match = re.fullmatch(r"/v1/users/(\d+)/avatar", path)
        if self.command in ("GET", "HEAD") and (path == "/v1/avatar" or avatar_match):
            if avatar_match:
                with backend.connect() as db:
                    exists = db.execute("SELECT id FROM users WHERE id=?", (int(avatar_match[1]),)).fetchone()
                if not exists:
                    raise ApiError(404, "User not found.")
            else:
                backend.current_user(self.cookie_value(SESSION_COOKIE))
            # Original test avatar: classic R6 body, no external worn assets.
            return self.reply(200, {
                "scales": {"height": 1, "width": 1, "head": 1, "depth": 1,
                           "proportion": 0, "bodyType": 0},
                "playerAvatarType": "R6",
                "bodyColors": {"headColorId": 24, "torsoColorId": 23,
                               "leftArmColorId": 24, "rightArmColorId": 24,
                               "leftLegColorId": 119, "rightLegColorId": 119},
                "assets": [], "emotes": []
            })
        if path == "/v1/avatar/metadata" and self.command in ("GET", "HEAD"):
            return self.reply(200, {
                "enableDefaultClothingMessage": False, "isAvatarScaleEmbeddedInTab": True,
                "isBodyTypeScaleOutOfTab": True, "scaleHeightIncrement": 0.05,
                "scaleWidthIncrement": 0.05, "scaleHeadIncrement": 0.05,
                "scaleProportionIncrement": 0.05, "scaleBodyTypeIncrement": 0.05,
                "supportProportionAndBodyType": False,
                "showDefaultClothingMessageOnPageLoad": False,
                "areThreeDeeThumbsEnabled": False
            })
        if path in ("/my/balance", "/v1/user/currency") and self.command in ("GET", "HEAD"):
            user = backend.current_account(self.cookie_value(SESSION_COOKIE))
            return self.reply(200, {"robux": user["robux"]})
        if path.startswith(realtime.PREFIX + "/") and self.command in ("GET", "POST"):
            user = backend.current_user(self.cookie_value(SESSION_COOKIE))
            query = parse_qs(url.query)
            action = path[len(realtime.PREFIX) + 1:]
            if action == "negotiate":
                protocol = query.get("clientProtocol", ["1.5"])[0]
                if protocol not in ("1.2", "1.3", "1.4", "1.5"):
                    raise ApiError(400, "Unsupported legacy SignalR protocol.")
                return self.reply(200, realtime.negotiate(backend.realtime_secret, user["id"], protocol))
            token = query.get("connectionToken", [""])[0]
            if not realtime.valid(backend.realtime_secret, token, user["id"]):
                raise ApiError(403, "Invalid or expired realtime connection.")
            if action in ("connect", "reconnect", "poll", "start", "abort"):
                if query.get("transport", [""])[0] != "longPolling":
                    raise ApiError(400, "Only longPolling is available.")
                if action == "start":
                    return self.reply(200, {"Response": "started"})
                if action == "abort":
                    return self.reply(200)
                if action == "poll":
                    time.sleep(2)  # Bound request rate while no events exist.
                payload = {"C": "0", "M": []}
                if action == "connect":
                    payload["S"] = 1
                return self.reply(200, payload)
            raise ApiError(404, "Realtime operation is not implemented.")
        if path == "/users/account-info" and self.command in ("GET", "POST", "HEAD"):
            user = backend.current_account(self.cookie_value(SESSION_COOKIE))
            return self.reply(200, {**user, "userId": user["id"], "username": user["name"],
                                    "membershipType": 4 if user["isPremium"] else 0, "RobuxBalance": user["robux"], "MembershipType": 4 if user["isPremium"] else 0})
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
            return self.reply(200, {"userId": user["id"], "username": user["name"],
                                   "displayName": user["displayName"], "membershipType": 0,
                                   "user": user, "isBanned": False},
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
    database_url = os.getenv("DATABASE_URL")
    if os.getenv("LUXBLOX_REQUIRE_PERSISTENT_DATABASE") == "1" and not database_url:
        raise RuntimeError("DATABASE_URL is required; refusing temporary account storage")
    try:
        backend = Backend(args.database, args.settings, not args.insecure_local_cookies, database_url)
    except Exception as exc:
        message = str(exc)
        if database_url:
            from urllib.parse import unquote
            parsed = urlsplit(database_url)
            for secret in (database_url, parsed.password, unquote(parsed.password or ""), parsed.username):
                if secret:
                    message = message.replace(secret, "[redacted]")
        message = re.sub(r"postgres(?:ql)?://[^\\s]+", "[redacted connection URL]", message)
        LOG.error("Database initialization failed (%s): %s", type(exc).__name__, message[:1500])
        raise RuntimeError("Cannot initialize configured account database") from None
    server = Server((args.host, args.port), backend)
    LOG.info("LuxBlox listening on %s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        backend.close()


if __name__ == "__main__":
    main()


