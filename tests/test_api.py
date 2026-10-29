import contextlib
import http.client
from http.cookies import SimpleCookie
import io
import json
import logging
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from server.app import Backend, Server, SESSION_COOKIE


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = Path(self.tmp.name) / "test.sqlite3"
        self.backend = Backend(self.database, Path(__file__).parents[1] / "config/AndroidApp.json", False)
        self.server = Server(("127.0.0.1", 0), self.backend)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.cookies = {}
        self.token = None

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.tmp.cleanup()

    def request(self, method, path, body=None, raw=None, extra=None):
        headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items())}
        if self.token:
            headers["X-CSRF-TOKEN"] = self.token
        if body is not None:
            raw = json.dumps(body)
            headers["Content-Type"] = "application/json"
        headers.update(extra or {})
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            conn.request(method, path, body=raw, headers=headers)
            response = conn.getresponse()
            status = response.status
            for key, value in response.getheaders():
                if key.lower() == "set-cookie":
                    cookie = SimpleCookie(value)
                    self.cookies.update({k: v.value for k, v in cookie.items()})
                if key.lower() == "x-csrf-token":
                    self.token = value
            payload = response.read()
            return status, json.loads(payload) if payload else None
        finally:
            conn.close()

    def authenticated_post(self, path, body):
        result = self.request("POST", path, body)
        if result[0] == 403 and self.token:
            result = self.request("POST", path, body)
        return result

    def test_bootstrap_shape_and_methods(self):
        for route in ("/v1/settings/application", "/v2/settings/application"):
            for method in ("GET", "POST"):
                status, data = self.request(method, route + "?applicationName=AndroidApp")
                self.assertEqual(status, 200)
                self.assertIsInstance(data["applicationSettings"], dict)
                self.assertTrue(all(isinstance(v, str) for v in data["applicationSettings"].values()))
        self.assertEqual(self.request("GET", "/v1/settings/application?applicationName=../secret")[0], 400)

    def test_universal_app_configuration_returns_content(self):
        prefix = "/universal-app-configuration/v1/behaviors/"
        status, policy = self.request("GET", prefix + "app-policy/content")
        self.assertEqual(status, 200)
        self.assertTrue(policy["UseBottomBar"])
        self.assertEqual(policy["Routes"]["auth"]["signup"], "v2/signup")
        self.assertFalse(policy["OfficialStoreEnabled"])
        status, patch = self.request("GET", prefix + "app-patch/content")
        self.assertEqual(status, 200)
        self.assertEqual(patch, {"SchemeVersion": "1", "CanaryUserIds": [], "CanaryPercentage": 0})
        for name in ("app-policy", "app-patch"):
            self.assertEqual(self.request("HEAD", prefix + name + "/content"), (200, None))
            self.assertEqual(self.request("POST", prefix + name + "/content", {})[0], 404)

    def test_unknown_routes_are_not_false_success(self):
        self.assertEqual(self.request("GET", "/game/join")[0], 404)
        self.assertEqual(self.request("GET", "/v2/signup")[0], 404)

    def test_zero_currency_is_explicit_and_requires_login(self):
        for path in ("/my/balance", "/v1/user/currency"):
            self.assertEqual(self.request("GET", path)[0], 401)
        self.authenticated_post("/v2/signup", {"username": "BalanceTest", "password": "test-password"})
        for path in ("/my/balance", "/v1/user/currency"):
            self.assertEqual(self.request("GET", path), (200, {"robux": 0}))
        data = self.request("GET", "/users/account-info")[1]
        self.assertEqual(data["RobuxBalance"], 0)
        self.assertEqual(data["MembershipType"], 0)

    def test_legacy_signalr_handshake_and_token_isolation(self):
        prefix = "/realtime/notifications/signalr/"
        self.assertEqual(self.request("GET", prefix + "negotiate")[0], 401)
        self.authenticated_post("/v2/signup", {"username": "SignalTest", "password": "test-password"})
        status, negotiation = self.request("GET", prefix + "negotiate?clientProtocol=1.5")
        self.assertEqual(status, 200)
        self.assertFalse(negotiation["TryWebSockets"])
        self.assertEqual(negotiation["ProtocolVersion"], "1.5")
        query = urlencode({"transport": "longPolling", "connectionToken": negotiation["ConnectionToken"]})
        self.assertEqual(self.request("GET", prefix + "connect?" + query), (200, {"C": "0", "M": [], "S": 1}))
        self.assertEqual(self.request("GET", prefix + "start?" + query), (200, {"Response": "started"}))
        self.assertEqual(self.request("GET", prefix + "poll?" + query), (200, {"C": "0", "M": []}))
        self.assertEqual(self.request("GET", prefix + "negotiate?clientProtocol=9")[0], 400)
        self.assertEqual(self.request("GET", prefix + "connect?transport=longPolling&connectionToken=bad")[0], 403)
        self.authenticated_post("/v2/signup", {"username": "OtherSignal", "password": "test-password"})
        self.assertEqual(self.request("GET", prefix + "start?" + query)[0], 403)

    def test_native_interface_configuration_is_present(self):
        flags = self.request("GET", "/v1/settings/application?applicationName=AndroidApp")[1]["applicationSettings"]
        self.assertEqual(flags["FFlagEnableJavascriptHybrid2"], "True")
        self.assertEqual(flags["FFlagDatamodelServicesConnectionFix2"], "True")

    def test_lua_path_namespaces_preserve_sessions_and_classic_routes(self):
        self.authenticated_post("/auth/v2/signup", {"username": "NamespaceTest", "password": "test-password"})
        user = self.request("GET", "/users/v1/users/authenticated")[1]
        user_id = user["id"]
        self.assertEqual(self.request("GET", "/economy/v1/user/currency"), (200, {"robux": 0}))
        self.assertEqual(self.request("GET", f"/users/v1/users/{user_id}")[1]["name"], "NamespaceTest")
        self.assertEqual(self.request("GET", f"/friends/v1/users/{user_id}/friends/count"), (200, {"count": 0}))
        self.assertEqual(self.request("GET", "/users/account-info")[0], 200)
        self.assertEqual(self.request("GET", "/apis/universal-app-configuration/v1/behaviors/app-policy/content")[0], 200)
        self.assertEqual(self.request("GET", "/avatar/v1/not-implemented")[0], 404)

    def test_classic_username_validation_matches_client_codes(self):
        for username, code in [("Luxius", 0), ("Lux_Blox", 0), ("ab", 3),
                               ("", 9), ("a b", 6), ("имя", 7), ("_name", 4),
                               ("name_", 4), ("a_b_c", 5)]:
            status, data = self.request("GET", "/signup/is-username-valid?" + urlencode({"username": username}))
            self.assertEqual(status, 200)
            self.assertEqual(data["ErrorCode"], code)
            self.assertEqual(data["IsValid"], code == 0)
            self.assertIsInstance(data["ErrorMessage"], str)
        self.backend.register("TakenName", "test-password")
        self.assertEqual(self.request("GET", "/signup/is-username-valid?username=takenname")[1]["ErrorCode"], 1)

    def test_classic_password_validation_and_signup_agree(self):
        for password, code in [("1234567", 2), ("12345678", 0), ("Luxius123", 3), ("x" * 129, 2)]:
            url = "/signup/is-password-valid?" + urlencode({"username": "Luxius123", "password": password})
            status, data = self.request("GET", url)
            self.assertEqual(status, 200)
            self.assertEqual(data["ErrorCode"], code)
            self.assertEqual(data["IsValid"], code == 0)
        result = self.authenticated_post("/v2/signup", {"username": "Luxius123", "password": "Luxius123"})
        self.assertEqual(result[0], 400)
        self.assertEqual(result[1]["errors"][0]["code"], 3)

    def test_classic_account_info_requires_session(self):
        self.assertEqual(self.request("GET", "/users/account-info")[0], 401)
        status, data = self.authenticated_post("/v2/signup", {"username": "Profile", "password": "test-password"})
        self.assertEqual(status, 200)
        for method in ("GET", "POST"):
            status, profile = self.request(method, "/users/account-info")
            self.assertEqual(status, 200)
            self.assertEqual(profile["userId"], data["userId"])
            self.assertEqual(profile["username"], "Profile")

    def test_telemetry_is_acknowledged_without_storing_data(self):
        self.assertEqual(self.request("POST", "/mobile/pbe", raw="discarded")[0], 200)
        self.assertEqual(self.request("GET", "/v1.1/Counters/Increment?apiKey=not-logged")[0], 200)

    def test_startup_device_version_and_experiments(self):
        for method in ("GET", "POST"):
            status, data = self.request(method, "/device/initialize")
            self.assertEqual(status, 200)
            self.assertGreater(data["browserTrackerId"], 0)
            self.assertLess(data["browserTrackerId"], 2**53)
            self.assertIsNone(data["appDeviceIdentifier"])
            for path in ("/mobileapi/check-app-version", "/v1/mobile-client-version"):
                self.assertEqual(self.request(method, path)[1], {"data": {"UpgradeAction": "None"}})
            self.assertEqual(self.request(method, "/v1/enrollments")[1], {"data": []})
            self.assertEqual(self.request(method, "/v1/get-enrollments")[1], [])

    def test_registration_login_session_and_logout(self):
        credentials = {"username": "Luxius", "password": "test-only-password"}
        status, data = self.authenticated_post("/v2/signup", credentials)
        self.assertEqual(status, 200)
        user_id = data["userId"]
        token = self.cookies[SESSION_COOKIE]
        self.assertEqual(self.request("GET", "/v1/users/authenticated")[1]["id"], user_id)
        with self.backend.connect() as db:
            stored = db.execute("SELECT * FROM users").fetchone()
            self.assertNotEqual(stored["password_hash"], credentials["password"].encode())
            self.assertNotEqual(db.execute("SELECT token_hash FROM sessions").fetchone()[0], token)
        self.assertEqual(self.authenticated_post("/v2/logout", {})[0], 200)
        self.assertEqual(self.request("GET", "/v1/users/authenticated")[0], 401)
        status, data = self.authenticated_post("/v2/login", {"ctype": "Username", "cvalue": "luxius", "password": credentials["password"]})
        self.assertEqual(status, 200)
        self.assertEqual(data["user"]["id"], user_id)
        self.assertEqual(self.authenticated_post("/v1/login", {"username": "Luxius", "password": "wrong"})[0], 403)
        self.assertEqual(self.authenticated_post("/v2/signup", credentials)[0], 409)

    def test_csrf_is_bound_to_cookie(self):
        body = {"username": "Luxius", "password": "test-password"}
        self.assertEqual(self.request("POST", "/v2/signup", body)[0], 403)
        self.cookies.clear()
        self.assertEqual(self.request("POST", "/v2/signup", body)[0], 403)

    def test_secure_cookie_default(self):
        self.backend.secure_cookies = True
        conn = http.client.HTTPConnection(*self.server.server_address)
        conn.request("POST", "/v2/login")
        response = conn.getresponse()
        value = response.getheader("Set-Cookie")
        self.assertIn("Secure", value)
        self.assertIn("HttpOnly", value)
        self.assertIn("SameSite=Lax", value)
        response.read()
        conn.close()

    def test_expired_session_and_persistence(self):
        user = self.backend.register("Persist", "long-test-password")
        token = self.backend.session(user["id"])
        reopened = Backend(self.database, Path(__file__).parents[1] / "config/AndroidApp.json")
        self.assertEqual(reopened.current_user(token)["id"], user["id"])
        with self.backend.connect() as db:
            db.execute("UPDATE sessions SET expires=0")
        self.cookies[SESSION_COOKIE] = token
        self.assertEqual(self.request("GET", "/v1/users/authenticated")[0], 401)

    def test_bad_json_and_body_limit(self):
        self.request("POST", "/v2/login", {})  # acquire a CSRF cookie and token
        self.assertEqual(self.request("POST", "/v2/login", raw="{bad", extra={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/v2/login", raw="{}", extra={"Content-Length": "70000", "Content-Type": "application/json"})[0], 413)
        self.assertEqual(self.authenticated_post("/v2/signup", {"username": "ab", "password": "short"})[0], 400)

    def test_rate_limit(self):
        self.request("POST", "/v2/login", {})
        for _ in range(20):
            self.request("POST", "/v2/login", {})
        self.assertEqual(self.request("POST", "/v2/login", {})[0], 429)

    def test_logs_do_not_contain_query_or_password(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logger = logging.getLogger("luxblox")
        previous = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            self.request("GET", "/mobile/pbe?token=secret-query")
            self.authenticated_post("/v2/login", {"username": "user", "password": "secret-password"})
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)
        self.assertNotIn("secret-query", output.getvalue())
        self.assertNotIn("secret-password", output.getvalue())
        self.assertIn("/mobile/pbe", output.getvalue())

    def test_default_avatar_routes_and_authentication(self):
        self.assertEqual(self.request("GET", "/avatar/v1/avatar")[0], 401)
        status, user = self.authenticated_post("/v2/signup", {"username": "AvatarTest", "password": "test-password"})
        self.assertEqual(status, 200)
        status, avatar = self.request("GET", "/avatar/v1/avatar")
        self.assertEqual(status, 200)
        self.assertEqual(avatar["playerAvatarType"], "R6")
        self.assertEqual(avatar["assets"], [])
        self.assertEqual(len(avatar["bodyColors"]), 6)
        self.assertEqual(self.request("GET", "/avatar/v1/users/" + str(user["userId"]) + "/avatar")[1], avatar)
        self.assertEqual(self.request("GET", "/avatar/v1/users/999999999/avatar")[0], 404)
        self.assertFalse(self.request("GET", "/avatar/v1/avatar/metadata")[1]["areThreeDeeThumbsEnabled"])



if __name__ == "__main__":
    unittest.main()
