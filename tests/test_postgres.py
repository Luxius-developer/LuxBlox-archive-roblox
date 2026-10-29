"""Run only against the explicitly configured disposable PostgreSQL test DB."""
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from server.app import Backend, ApiError


@unittest.skipUnless(os.getenv('LUXBLOX_TEST_POSTGRES_URL'), 'PostgreSQL integration URL not configured')
class PostgresTests(unittest.TestCase):
    def backend(self):
        return Backend('/unused/sqlite.sqlite3', Path(__file__).parents[1] / 'config/AndroidApp.json',
                       database_url=os.environ['LUXBLOX_TEST_POSTGRES_URL'])

    def test_account_and_session_survive_backend_recreation(self):
        first = self.backend()
        name = 'P' + secrets.token_hex(8)
        user = first.register(name, 'persistent-test-password')
        token = first.session(user['id'])
        second = self.backend()
        self.assertEqual(second.login(name.lower(), 'persistent-test-password'), user)
        self.assertEqual(second.current_user(token), user)
        self.assertEqual(second.validate_username(name.upper())[0], 1)
        with self.assertRaises(ApiError) as error:
            second.login(name, 'wrong-password')
        self.assertEqual(error.exception.status, 403)
        with second.connect() as db:
            row = db.execute('SELECT salt,password_hash FROM users WHERE id=?', (user['id'],)).fetchone()
            self.assertIsInstance(row['salt'], bytes)
            self.assertEqual(len(row['salt']), 16)
            self.assertNotEqual(row['password_hash'], b'persistent-test-password')
            db.execute('UPDATE sessions SET expires=0 WHERE token_hash=?',
                       (__import__('hashlib').sha256(token.encode()).hexdigest(),))
        with self.assertRaises(ApiError):
            first.current_user(token)

    def test_unique_user_index_rolls_back_failed_transaction(self):
        backend = self.backend()
        name = 'P' + secrets.token_hex(8)
        user = backend.register(name, 'persistent-test-password')
        with self.assertRaises(backend.integrity_errors):
            with backend.connect() as db:
                db.execute('INSERT INTO users(username,salt,password_hash) VALUES(?,?,?)',
                           (name.upper(), b'1234567890123456', b'hash'))
        self.assertEqual(backend.login(name, 'persistent-test-password')['id'], user['id'])


class PersistentConfigurationTests(unittest.TestCase):
    def test_required_external_storage_never_creates_sqlite_fallback(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            sqlite_path = Path(directory) / 'must-not-exist.sqlite3'
            env = dict(os.environ, LUXBLOX_REQUIRE_PERSISTENT_DATABASE='1')
            env.pop('DATABASE_URL', None)
            result = subprocess.run([sys.executable, '-m', 'server.app', '--database', str(sqlite_path)],
                                    env=env, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'refusing temporary account storage', result.stderr)
            self.assertFalse(sqlite_path.exists())
