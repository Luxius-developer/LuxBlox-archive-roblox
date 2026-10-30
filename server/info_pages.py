from html import escape
from server.account_pages import STYLE


def render(path):
    key=path.rsplit('/',1)[-1]
    title,body={
        'careers':('Работа','<p>Vortix Studio сейчас не принимает заявки на работу.</p>'),
        'parents':('Родителям','<p>LuxBlox — независимый архивный проект. Настройки входящих сообщений, заявок в друзья и видимости инвентаря доступны в разделе конфиденциальности.</p><a href="/my/account/privacy">Открыть настройки</a>'),
        'terms':('Условия','<p>LuxBlox находится в разработке. Реальные платежи отключены. Robux и Premium в этом проекте действуют только внутри LuxBlox.</p>'),
        'terms-of-service':('Условия','<p>Реальные платежи отключены. Игровой сервер ещё не запущен.</p>'),
        'licenses':('Сторонние компоненты','<p>Звуковой движок: FMOD by Firelight Technologies / Firelight Studios. FMOD является компонентом исходного клиента. Авторство этой библиотеки не относится к Vortix Studio.</p>'),
        'us':('О проекте','<p>LuxBlox · Vortix Studio. Независимый архивный проект.</p>'),
    }.get(key,('Сведения','<p>LuxBlox · Vortix Studio</p>'))
    return ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+'</title><style>'+STYLE+'</style><main><h1>'+escape(title)+'</h1><section>'+body+'</section><a href="/info/licenses">Сторонние компоненты</a></main></html>').encode()
