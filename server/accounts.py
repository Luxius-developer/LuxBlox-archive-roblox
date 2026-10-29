"""Persistent test currency and account edits. No real payments."""
import hashlib
import hmac
import secrets

OFFERS = (80, 400, 800, 1700, 10000)
USERNAME_COST = 500


def initialize(db, postgres=False):
    db.execute('''CREATE TABLE IF NOT EXISTS account_profiles (
        user_id BIGINT PRIMARY KEY REFERENCES users(id),
        display_name TEXT,
        robux BIGINT NOT NULL DEFAULT 0 CHECK (robux >= 0 AND robux <= 1000000000)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS wallet_grants (
        user_id BIGINT NOT NULL REFERENCES users(id), request_id TEXT NOT NULL,
        amount INTEGER NOT NULL, PRIMARY KEY(user_id, request_id)
    )''')


def profile(backend, user_id):
    with backend.connect() as db:
        row = db.execute('''SELECT users.username, account_profiles.display_name,
            COALESCE(account_profiles.robux,0) AS robux FROM users
            LEFT JOIN account_profiles ON account_profiles.user_id=users.id WHERE users.id=?''', (user_id,)).fetchone()
    from server.features import flags
    return {'username': row['username'], 'displayName': row['display_name'] or row['username'], 'robux': row['robux'], **flags(backend,user_id)}


def token(backend, user_id, session):
    return hmac.new(backend.csrf_secret, f'account:{user_id}:{session}'.encode(), 'sha256').hexdigest()


def mutate(backend, user_id, session, form):
    from server.errors import ApiError
    with backend.connect() as db:
        if not backend.is_postgres:
            db.execute('BEGIN IMMEDIATE')
        suffix = ' FOR UPDATE' if backend.is_postgres else ''
        row = db.execute('SELECT username,salt,password_hash FROM users WHERE id=?' + suffix, (user_id,)).fetchone()
        db.execute('INSERT INTO account_profiles(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING', (user_id,))
        action = form.get('action', '')
        if action == 'grant':
            if user_id != backend.owner_user_id:
                raise ApiError(403, 'Бесплатные Robux доступны только владельцу LuxBlox.')
            try:
                amount = int(form.get('amount', ''))
            except (ValueError, TypeError):
                raise ApiError(400, 'Выберите тестовый набор.') from None
            request_id = form.get('request_id', '')
            if amount not in OFFERS or len(request_id) != 32 or any(c not in '0123456789abcdef' for c in request_id):
                raise ApiError(400, 'Некорректный набор или номер операции.')
            inserted = db.execute('''INSERT INTO wallet_grants(user_id,request_id,amount)
                VALUES(?,?,?) ON CONFLICT(user_id,request_id) DO NOTHING RETURNING user_id''',
                (user_id, request_id, amount)).fetchone()
            if inserted:
                updated = db.execute('''UPDATE account_profiles SET robux=robux+?
                    WHERE user_id=? AND robux<=1000000000-? RETURNING robux''', (amount, user_id, amount)).fetchone()
                if not updated:
                    raise ApiError(409, 'Достигнут предел тестового баланса.')
            return 'Тестовые Robux сохранены.'
        if action == 'display_name':
            name = form.get('display_name', '').strip()
            if not 3 <= len(name) <= 20 or not all(c.isprintable() for c in name):
                raise ApiError(400, 'Отображаемое имя: от 3 до 20 видимых символов.')
            db.execute('UPDATE account_profiles SET display_name=? WHERE user_id=?', (name, user_id))
            return 'Отображаемое имя сохранено.'
        if action not in ('username', 'password'):
            raise ApiError(400, 'Неизвестная операция.')
        password = form.get('current_password', '')
        if not isinstance(password, str) or len(password) > 128 or not hmac.compare_digest(
                backend.password_hash(password, row['salt']), row['password_hash']):
            raise ApiError(403, 'Текущий пароль неверен.')
        if action == 'username':
            name = form.get('username', '')
            code, message = backend.validate_username(name)
            if code:
                raise ApiError(409 if code == 1 else 400, message)
            paid = db.execute('''UPDATE account_profiles SET robux=robux-?
                WHERE user_id=? AND robux>=? RETURNING robux''', (USERNAME_COST, user_id, USERNAME_COST)).fetchone()
            if not paid:
                raise ApiError(409, 'Для смены username нужно 500 Robux.')
            try:
                db.execute('UPDATE users SET username=? WHERE id=?', (name, user_id))
            except backend.integrity_errors:
                raise ApiError(409, 'Этот username уже занят.') from None
            return 'Username изменён. Списано 500 Robux.'
        new_password = form.get('new_password', '')
        code, message = backend.validate_password(row['username'], new_password)
        if code:
            raise ApiError(400, message)
        if new_password != form.get('confirm_password', ''):
            raise ApiError(400, 'Новые пароли не совпадают.')
        salt = secrets.token_bytes(16)
        db.execute('UPDATE users SET salt=?,password_hash=? WHERE id=?',
                   (salt, backend.password_hash(new_password, salt), user_id))
        db.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',
                   (user_id, hashlib.sha256(session.encode()).hexdigest()))
        return 'Пароль изменён. Остальные сеансы завершены.'
