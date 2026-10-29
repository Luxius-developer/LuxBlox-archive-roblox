"""Private messages for LuxBlox WebViews; not the native in-game chat protocol."""
from html import escape
import secrets
import time
from server.errors import ApiError
from server.account_pages import STYLE


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY, sender_id BIGINT NOT NULL REFERENCES users(id),
        recipient_id BIGINT NOT NULL REFERENCES users(id), body TEXT NOT NULL,
        created_at BIGINT NOT NULL, CHECK(length(body) BETWEEN 1 AND 500)
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS chat_sender_time ON chat_messages(sender_id,created_at)')
    db.execute('CREATE INDEX IF NOT EXISTS chat_recipient_time ON chat_messages(recipient_id,created_at)')


def messages(backend, user_id):
    with backend.connect() as db:
        rows = db.execute('''SELECT m.id,m.sender_id,m.recipient_id,m.body,m.created_at,
            s.username AS sender,r.username AS recipient FROM chat_messages m
            JOIN users s ON s.id=m.sender_id JOIN users r ON r.id=m.recipient_id
            WHERE m.sender_id=? OR m.recipient_id=? ORDER BY m.created_at DESC,m.id DESC LIMIT 100''', (user_id,user_id)).fetchall()
    return [dict(r) for r in reversed(rows)]


def send(backend, user_id, recipient, text):
    if not isinstance(recipient,str) or len(recipient)>20 or not isinstance(text,str):
        raise ApiError(400,'Укажите username получателя и текст.')
    text=text.strip()
    if not 1<=len(text)<=500 or not all(c.isprintable() or c=='\n' for c in text):
        raise ApiError(400,'Сообщение должно содержать от 1 до 500 видимых символов.')
    with backend.connect() as db:
        row=db.execute('SELECT id FROM users WHERE lower(username)=lower(?)',(recipient,)).fetchone()
        if not row:
            raise ApiError(404,'Получатель не найден.')
        if row['id']==user_id:
            raise ApiError(400,'Укажите username другого пользователя.')
        message_id=secrets.token_hex(16)
        db.execute('INSERT INTO chat_messages(id,sender_id,recipient_id,body,created_at) VALUES(?,?,?,?,?)',
                   (message_id,user_id,row['id'],text,time.time_ns()//1000))
    return message_id


def render(csrf, message='', error=False):
    e=lambda value:escape(str(value),quote=True)
    notice='<p role="status" class="message'+(' error' if error else '')+'">'+e(message)+'</p>' if message else ''
    return ('''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Сообщения — LuxBlox</title><style>'''+STYLE+'''textarea{box-sizing:border-box;width:100%;min-height:90px;padding:10px;font:16px Arial;border:1px solid #b8bec3}#history p{white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;background:white;border-bottom:1px solid #ddd}</style><header>Сообщения</header><main>'''+notice+'''<div id="history" aria-live="polite">Загрузка сообщений…</div><section><form method="post"><input type="hidden" name="csrf" value="'''+e(csrf)+'''"><label>Username получателя<input name="recipient" required maxlength="20" autocomplete="off"></label><label>Сообщение<textarea name="message" required maxlength="500"></textarea></label><button>Отправить</button></form></section><p class="muted">Личная переписка LuxBlox. Новые сообщения появляются автоматически.</p></main><script>async function refresh(){try{let r=await fetch('/luxblox/chat/messages',{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw Error();let j=await r.json(),box=document.getElementById('history');box.textContent='';j.data.forEach(function(m){let p=document.createElement('p'),b=document.createElement('b');b.textContent=m.sender+' → '+m.recipient;p.appendChild(b);p.appendChild(document.createTextNode('\\n'+m.body));box.appendChild(p)});if(!j.data.length)box.textContent='Пока нет сообщений.'}catch(e){document.getElementById('history').textContent='Не удалось обновить сообщения. Попробуем ещё раз.'}}refresh();setInterval(function(){if(!document.hidden)refresh()},8000)</script></html>''').encode()
