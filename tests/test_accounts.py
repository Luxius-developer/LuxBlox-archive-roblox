import concurrent.futures
import hashlib
from pathlib import Path
import secrets
import tempfile
import unittest
from server.app import Backend, ApiError
from server import accounts, account_pages


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'test.sqlite3'
        self.settings = Path(__file__).parents[1]/'config/AndroidApp.json'
        self.backend = Backend(self.path, self.settings, False)
        self.user = self.backend.register('WalletUser', 'old-password-123')
        self.session = self.backend.session(self.user['id'])

    def tearDown(self):
        self.tmp.cleanup()

    def mutate(self, action, **values):
        return accounts.mutate(self.backend, self.user['id'], self.session, {'action': action, **values})

    def balance(self):
        return self.backend.current_account(self.session)['robux']

    def grant(self, amount='800', request_id=None):
        return self.mutate('grant', amount=amount, request_id=request_id or secrets.token_hex(16))

    def test_duplicate_grants_and_concurrent_updates_persist(self):
        key = secrets.token_hex(16)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.grant(request_id=key), range(4)))
        self.assertEqual(self.balance(), 800)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.grant('80'), range(4)))
        self.assertEqual(self.balance(), 1120)
        reopened = Backend(self.path, self.settings, False)
        self.assertEqual(reopened.current_account(self.session)['robux'], 1120)
        with self.assertRaises(ApiError):
            self.grant('-500')
        self.assertEqual(self.balance(), 1120)

    def test_username_charge_password_checks_and_rollback(self):
        with self.assertRaises(ApiError):
            self.mutate('username', username='NewWallet', current_password='old-password-123')
        self.grant()
        with self.assertRaises(ApiError):
            self.mutate('username', username='NewWallet', current_password='wrong')
        self.assertEqual(self.balance(), 800)
        self.backend.register('TakenWallet', 'other-password')
        with self.assertRaises(ApiError):
            self.mutate('username', username='TakenWallet', current_password='old-password-123')
        self.assertEqual(self.balance(), 800)
        self.mutate('username', username='NewWallet', current_password='old-password-123')
        self.assertEqual(self.balance(), 300)
        self.assertEqual(self.backend.login('NewWallet', 'old-password-123')['id'], self.user['id'])
        with self.assertRaises(ApiError):
            self.backend.login('WalletUser', 'old-password-123')

    def test_display_password_and_revocation(self):
        self.mutate('display_name', display_name='Люксиус')
        self.assertEqual(self.backend.current_user(self.session)['displayName'], 'Люксиус')
        self.assertEqual(self.backend.login('WalletUser', 'old-password-123')['displayName'], 'Люксиус')
        other = self.backend.session(self.user['id'])
        with self.assertRaises(ApiError):
            self.mutate('password', current_password='old-password-123', new_password='new-password-123', confirm_password='different')
        self.mutate('password', current_password='old-password-123', new_password='new-password-123', confirm_password='new-password-123')
        self.assertEqual(self.backend.login('WalletUser', 'new-password-123')['id'], self.user['id'])
        with self.assertRaises(ApiError):
            self.backend.login('WalletUser', 'old-password-123')
        with self.assertRaises(ApiError):
            self.backend.current_user(other)
        self.assertEqual(self.backend.current_user(self.session)['id'], self.user['id'])

    def test_pages_escape_names_and_csrf_binds_session(self):
        profile = {'displayName':'<img src=x>', 'username':'WalletUser', 'robux': 80}
        page = account_pages.render(profile, 'csrf').decode()
        self.assertIn('&lt;img src=x&gt;', page)
        self.assertNotIn('<img src=x>', page)
        self.assertNotEqual(accounts.token(self.backend, self.user['id'], self.session), accounts.token(self.backend, self.user['id'], 'other'))
        self.assertNotIn('old-password', page)
