"""Small, self-contained pages for the Android client's classic WebViews."""
from html import escape
import secrets
from server.accounts import OFFERS, USERNAME_COST

STYLE = '''body{margin:0;background:#f2f4f5;color:#393b3d;font:16px Arial,sans-serif}header{background:#fff;border-bottom:1px solid #ccd0d3;padding:16px 20px;font-weight:bold;font-size:24px}main{max-width:640px;margin:auto;padding:18px}h1{font-size:28px;margin:10px 0 20px}h2{font-size:19px}section{background:#fff;border:1px solid #d6d9dc;border-radius:4px;padding:18px;margin:14px 0}p{line-height:1.5}.muted{color:#606770;font-size:14px}.balance{float:right;font-size:17px;padding-top:5px}button{background:#00a2ff;color:white;border:0;border-radius:4px;padding:12px 16px;font-weight:bold;font-size:16px;width:100%;cursor:pointer}button:disabled{opacity:.5}input{box-sizing:border-box;width:100%;padding:11px;border:1px solid #b8bec3;border-radius:4px;margin:7px 0 12px;font-size:16px}label{display:block;margin-top:10px}a{color:#0074bd}.message{padding:14px;background:#e1f4e8;border:1px solid #a4ccaf}.error{background:#fff0ed;border-color:#e2b1a7}.offers{display:grid;grid-template-columns:1fr 1fr;gap:12px}.offers section{margin:0;text-align:center}.offer{font-size:24px;font-weight:bold}.offer small{display:block;font-size:14px;margin:12px;color:#606770}nav{margin-bottom:18px}'''


def render(profile, csrf, page='account', message='', error=False):
    e = lambda value: escape(str(value), quote=True)
    hidden = '<input type="hidden" name="csrf" value="' + e(csrf) + '">'
    def form(action, content):
        return '<form method="post">' + hidden + '<input type="hidden" name="action" value="' + action + '">' + content + '</form>'
    notice = '<p role="status" class="message' + (' error' if error else '') + '">' + e(message) + '</p>' if message else ''
    if page == 'robux':
        title = 'Купить Robux'
        body = '<p>Наборы Robux для LuxBlox. Приём платежей пока отключён.</p><div class="offers">'
        for amount in OFFERS:
            owner = profile.get('isOwner',False)
            price = {80:49,400:199,800:399,1700:699,10000:1500}[amount]
            body += '<section><p class="offer">' + str(amount) + ' Robux<small>' + ('Бесплатно для владельца' if owner else str(price)+' ₽') + '</small></p>'
            if owner:
                body += form('grant', '<input type="hidden" name="amount" value="' + str(amount) + '"><input type="hidden" name="request_id" value="' + secrets.token_hex(16) + '"><button type="submit">Купить бесплатно</button>')
            else:
                body += '<a href="/checkout/unavailable">Купить</a>'
            body += '</section>'
        body += '</div><p class="muted">Баланс хранится в аккаунте LuxBlox. Эти Robux действуют только здесь.</p>'
    else:
        title = 'Информация об учётной записи'
        body = '<nav><a href="/my/account/security">Безопасность</a> · <a href="/my/account/notifications">Уведомления</a> · <a href="/my/account/billing">Оплата</a> · <a href="/my/account/privacy">Конфиденциальность</a> · <a href="/more">Ещё</a></nav><section><h2>Отображаемое имя</h2>' + form('display_name', '<label>Никнейм<input name="display_name" minlength="3" maxlength="20" required value="' + e(profile['displayName']) + '"></label><button>Сохранить бесплатно</button>') + '</section>'
        body += '<section><h2>Username</h2><p class="muted">Имя для входа. Смена стоит ' + str(USERNAME_COST) + ' Robux.</p>' + form('username', '<label>Новый username<input name="username" minlength="3" maxlength="20" required autocomplete="username" value="' + e(profile['username']) + '"></label><label>Текущий пароль<input type="password" name="current_password" required maxlength="128" autocomplete="current-password"></label><button>Изменить за 500 Robux</button>') + '</section>'
        body += '<section><h2>Пароль</h2>' + form('password', '<label>Текущий пароль<input type="password" name="current_password" required maxlength="128" autocomplete="current-password"></label><label>Новый пароль<input type="password" name="new_password" required minlength="8" maxlength="128" autocomplete="new-password"></label><label>Повторите новый пароль<input type="password" name="confirm_password" required minlength="8" maxlength="128" autocomplete="new-password"></label><button>Изменить пароль</button>') + '</section>'
    return ('<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + ' — LuxBlox</title><style>' + STYLE + '</style></head><body><header>LuxBlox<span class="balance">' + e(profile['robux']) + ' Robux</span></header><main><h1>' + title + '</h1>' + notice + body + '</main><script>let hash=location.hash.toLowerCase();let target=hash.includes("security")?"security":hash.includes("notification")?"notifications":hash.includes("billing")?"billing":hash.includes("privacy")?"privacy":"";if(target)location.replace("/my/account/"+target);document.querySelectorAll("form").forEach(function(f){f.addEventListener("submit",function(){f.querySelector("button").disabled=true})})</script></body></html>').encode()
