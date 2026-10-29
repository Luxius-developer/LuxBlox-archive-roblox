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
        self.backend.owner_user_id = 1
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

    def test_games_namespace_and_legacy_double_slash_urls(self):
        status, data = self.request("GET", "/games//v1/games/multiget-place-details?placeIds=1001,9999")
        self.assertEqual(status, 200)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["placeId"], 1001)
        self.assertFalse(data[0]["isPlayable"])
        self.assertEqual(data[0]["reasonProhibited"], "GameServerNotConfigured")
        status, listing = self.request("GET", "/games/v1/games/list?sortToken=luxblox")
        self.assertEqual(status, 200)
        self.assertEqual(listing["games"][0]["universeId"], 1001)
        self.assertEqual(self.request("GET", "/games/v1/games?universeIds=9999"), (200, {"data": []}))
        self.assertEqual(self.request("GET", "/catalog/v1/games/list")[0], 404)

    def test_robux_webview_serves_html_without_payment_actions(self):
        self.assertEqual(self.request("GET", "/upgrades/robux")[0], 401)
        self.authenticated_post("/v2/signup", {"username": "WebBalance", "password": "test-password"})
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            conn.request("GET", "/upgrades/robux", headers={"Cookie": "; ".join(f"{k}={v}" for k,v in self.cookies.items())})
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(response.getheader("Content-Type").startswith("text/html"))
            self.assertIn("Купить бесплатно", response.read().decode())
        finally:
            conn.close()

    def test_web_wallet_form_csrf_idempotency_and_balance_api(self):
        import re
        self.authenticated_post("/v2/signup", {"username": "WebWallet", "password": "test-password"})
        def web(method, path, body=None):
            conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
            headers = {"Cookie": "; ".join(f"{k}={v}" for k,v in self.cookies.items())}
            if body is not None:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            try:
                conn.request(method, path, body=urlencode(body) if body is not None else None, headers=headers)
                r = conn.getresponse()
                return r.status, dict(r.getheaders()), r.read().decode()
            finally:
                conn.close()
        status, headers, html = web("GET", "/upgrades/robux")
        self.assertEqual(status, 200)
        csrf = re.search(r'name="csrf" value="([a-f0-9]+)"', html)[1]
        key = re.search(r'name="request_id" value="([a-f0-9]+)"', html)[1]
        form = {"action": "grant", "amount": "800", "request_id": key}
        self.assertEqual(web("POST", "/upgrades/robux", form)[0], 403)
        self.assertEqual(self.request("GET", "/my/balance"), (200, {"robux": 0}))
        form["csrf"] = csrf
        self.assertEqual(web("POST", "/upgrades/robux", form)[0], 303)
        self.assertEqual(web("POST", "/upgrades/robux", form)[0], 303)
        self.assertEqual(self.request("GET", "/my/balance"), (200, {"robux": 800}))
        self.assertEqual(self.request("GET", "/users/account-info")[1]["RobuxBalance"], 800)
        self.assertIn("800 Robux", web("GET", "/upgrades/robux")[2])
        self.assertEqual(web("POST", "/my/account", {"action":"display_name", "display_name":"New Display", "csrf":csrf})[0], 303)
        profile = self.request("GET", "/users/v1/users/authenticated")[1]
        self.assertEqual(self.request("GET", f"/users/v1/users/{profile['id']}")[1]["displayName"], "New Display")
        self.assertEqual(web("POST", "/my/account", form)[0], 400)
        status, _, html = web("GET", "/my/account")
        self.assertEqual(status, 200)
        self.assertIn("Изменить за 500 Robux", html)
        self.assertNotIn("test-password", html)

    def test_private_chat_api_authentication_and_visibility(self):
        self.assertEqual(self.request("GET", "/luxblox/chat/messages")[0], 401)
        self.authenticated_post("/v2/signup", {"username":"ChatSender", "password":"test-password"})
        sender_cookies=dict(self.cookies)
        self.authenticated_post("/v2/signup", {"username":"ChatReceiver", "password":"test-password"})
        receiver_cookies=dict(self.cookies)
        self.cookies=sender_cookies
        status, sent=self.authenticated_post("/luxblox/chat/send", {"recipient":"ChatReceiver", "message":"hello <script>"})
        self.assertEqual(status,200)
        self.cookies=receiver_cookies
        self.assertEqual(self.request("GET", "/luxblox/chat/messages")[1]["data"][0]["id"],sent["id"])
        self.authenticated_post("/v2/signup", {"username":"ChatOther", "password":"test-password"})
        self.assertEqual(self.request("GET", "/luxblox/chat/messages"),(200,{"data":[]}))

    def test_web_login_requires_csrf_and_sets_a_session(self):
        import re
        self.backend.register('WebSignIn','test-password')
        self.assertEqual(self.request('GET','/more')[0],303)
        def form_request(method,body=None):
            conn=http.client.HTTPConnection(*self.server.server_address,timeout=5)
            headers={'Cookie':'; '.join(f'{k}={v}' for k,v in self.cookies.items())}
            if body is not None:headers['Content-Type']='application/x-www-form-urlencoded'
            try:
                conn.request(method,'/login',body=urlencode(body) if body is not None else None,headers=headers)
                r=conn.getresponse()
                for k,v in r.getheaders():
                    if k.lower()=='set-cookie':
                        c=SimpleCookie(v);self.cookies.update({k:v.value for k,v in c.items()})
                return r.status,r.read()
            finally:conn.close()
        status,html=form_request('GET');self.assertEqual(status,200)
        csrf=re.search(rb'name="csrf" value="([a-f0-9]+)"',html)[1].decode()
        self.assertEqual(form_request('POST',{'username':'WebSignIn','password':'test-password'})[0],403)
        self.assertEqual(form_request('POST',{'username':'WebSignIn','password':'test-password','csrf':csrf})[0],303)
        self.assertEqual(self.request('GET','/users/v1/users/authenticated')[1]['name'],'WebSignIn')

    def test_social_catalog_owner_and_settings_web_flows(self):
        import re
        def web(method,path,form=None,html=True):
            conn=http.client.HTTPConnection(*self.server.server_address,timeout=5)
            headers={'Cookie':'; '.join(f'{k}={v}' for k,v in self.cookies.items())}
            if html:headers['Accept']='text/html'
            if form is not None:headers['Content-Type']='application/x-www-form-urlencoded'
            try:
                conn.request(method,path,body=urlencode(form) if form is not None else None,headers=headers)
                r=conn.getresponse();return r.status,r.read()
            finally:conn.close()
        self.authenticated_post('/v2/signup',{'username':'ProjectOwner','password':'owner-password'})
        owner=dict(self.cookies)
        status,html=web('GET','/admin');self.assertEqual(status,200)
        csrf=re.search(rb'name="csrf" value="([a-f0-9]+)"',html)[1].decode()
        self.assertEqual(web('POST','/admin',{'action':'admin_flags','target':'1','verified':'on','premium':'on'})[0],403)
        self.assertEqual(web('POST','/admin',{'action':'admin_flags','target':'1','verified':'on','premium':'on','csrf':csrf})[0],303)
        self.assertTrue(self.request('GET','/users/v1/users/1')[1]['hasVerifiedBadge'])
        self.assertEqual(self.request('GET','/users/account-info')[1]['MembershipType'],4)
        self.assertIn('Админ-панель'.encode(),web('GET','/more')[1])
        for path in ['/users/friends','/my/avatar','/catalog','/users/1/inventory','/my/account/security','/my/account/billing','/my/account/notifications','/premium/membership','/games/1001/Starter-Obby']:
            self.assertEqual(web('GET',path)[0],200,path)
        self.authenticated_post('/v2/signup',{'username':'OtherUser','password':'other-password'})
        other=dict(self.cookies)
        self.assertEqual(web('GET','/admin')[0],403)
        status,wallet=web('GET','/upgrades/robux');self.assertNotIn('Купить бесплатно'.encode(),wallet)
        self.assertIn('1500 ₽'.encode(),wallet)
        other_csrf=re.search(rb'name="csrf" value="([a-f0-9]+)"',web('GET','/my/account')[1])[1].decode()
        self.assertEqual(web('POST','/upgrades/robux',{'action':'grant','amount':'10000','request_id':'a'*32,'csrf':other_csrf})[0],403)
        self.assertEqual(web('GET','/checkout/unavailable')[0],404)
        self.cookies=owner
        self.assertEqual(self.authenticated_post('/friends/v1/users/2/request-friendship',{})[0],200)
        self.cookies=other
        self.assertEqual(self.request('GET','/friends/v1/my/friends/requests')[1]['data'][0]['id'],1)
        self.assertEqual(self.authenticated_post('/friends/v1/users/1/accept-friend-request',{})[0],200)
        self.assertEqual(self.request('GET','/friends/v1/users/2/friends')[1]['data'][0]['id'],1)
        items=self.request('GET','/catalog/v1/search/items/details')[1]['data'];self.assertEqual(items[0]['id'],6001)
        self.assertEqual(self.authenticated_post('/economy/v1/purchases/products/6001',{})[0],200)
        self.assertEqual(self.authenticated_post('/avatar/v1/avatar/set-wearing-assets',{'assetIds':[6001]})[0],200)
        self.assertEqual(self.request('GET','/avatar/v1/avatar')[1]['assets'][0]['id'],6001)
        self.assertEqual(self.request('GET','/inventory/v1/users/2/assets/11')[1]['data'][0]['assetId'],6001)
        self.assertIn(b'ShirtTemplate',web('GET','/asset/?id=6001',html=False)[1])
        self.assertTrue(web('GET','/asset/?id=7001',html=False)[1].startswith(b'\x89PNG'))
        self.assertEqual(self.request('PATCH','/games/v1/games/1001/votes',{'isUpVote':True})[0],200)
        self.assertEqual(self.request('PATCH','/games/v1/games/1001/votes',{'isUpVote':True})[0],200)
        self.assertEqual(self.request('GET','/games/v1/games/1001/votes')[1]['upVotes'],1)
        self.assertEqual(self.request('GET','/Game/PlaceLauncher.ashx?placeId=1001')[0],503)

    def test_legacy_chat_v2_conversation_and_message_routes(self):
        self.assertEqual(self.request("GET", "/chat/v2/get-user-conversations")[0], 401)
        self.authenticated_post("/v2/signup", {"username":"LegacyChatA", "password":"test-password"})
        a_cookies = dict(self.cookies)
        a_id = self.request("GET", "/users/v1/users/authenticated")[1]["id"]
        self.authenticated_post("/v2/signup", {"username":"LegacyChatB", "password":"test-password"})
        b_cookies = dict(self.cookies)
        b_id = self.request("GET", "/users/v1/users/authenticated")[1]["id"]
        self.cookies = a_cookies
        status, created = self.authenticated_post("/chat/v2/start-one-to-one-conversation",
                                                  {"participantuserId": b_id})
        self.assertEqual(status, 200, created)
        conversation_id = created["id"]
        listing = self.request("GET", "/chat/v2/get-user-conversations?pageNumber=1&pageSize=20")[1]
        self.assertEqual([c["id"] for c in listing], [conversation_id])
        status, sent = self.authenticated_post("/chat/v2/send-message", {
            "conversationId": conversation_id, "message": "hello"})
        self.assertEqual(status, 200)
        self.cookies = b_cookies
        received = self.request("GET", f"/chat/v2/get-conversation-messages?conversationId={conversation_id}")[1]
        self.assertEqual(received[0]["content"], "hello")
        self.assertEqual(received[0]["id"], sent["id"])
        self.assertEqual(self.request("GET", f"/chat/v2/get-conversation-messages?conversationId={conversation_id}")[0], 200)
        self.authenticated_post("/v2/signup", {"username":"LegacyChatC", "password":"test-password"})
        self.assertEqual(self.request("GET", f"/chat/v2/get-conversation-messages?conversationId={conversation_id}")[0], 404)
        self.cookies = a_cookies
        self.assertEqual(self.request("GET", "/chat/v2/chat-settings")[1]["isChatEnabled"], True)

    def test_legacy_user_profile_and_avatar_thumbnail_contract(self):
        self.authenticated_post("/v2/signup", {"username":"LegacyProfile", "password":"test-password"})
        user_id = self.request("GET", "/users/v1/users/authenticated")[1]["id"]
        profile = self.request("GET", f"/users/{user_id}/profile")[1]
        self.assertEqual(profile["UserId"], user_id)
        self.assertEqual(profile["Username"], "LegacyProfile")
        self.assertTrue(profile["AvatarFinal"])
        thumb = self.request("GET", f"/thumbnails/v1/users/avatar?userIds={user_id}&size=150x150&format=png")[1]
        self.assertEqual(thumb["data"][0]["state"], "Completed")
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            conn.request("GET", "/static/avatar-default.png")
            image = conn.getresponse()
            self.assertEqual(image.status, 200)
            self.assertEqual(image.getheader("Content-Type"), "image/png")
            self.assertTrue(image.read().startswith(b"\x89PNG"))
        finally:
            conn.close()

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
