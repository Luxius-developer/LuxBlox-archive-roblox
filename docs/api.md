# API прототипа

Все пути обслуживаются одним процессом. Разделение по старым поддоменам пока не реализовано.

| Метод | Путь | Ответ/назначение |
|---|---|---|
| GET, HEAD | `/healthz` | состояние процесса, не проверка Android-совместимости |
| GET, POST, HEAD | `/v1/settings/application?applicationName=AndroidApp` | `config/AndroidApp.json` |
| GET, POST, HEAD | `/v2/settings/application?applicationName=AndroidApp` | тот же профиль |
| GET, POST, HEAD | `/mobile/pbe`, `/client/pbe` | 200 без тела, данные не сохраняются |
| GET, POST, HEAD | `/v1.1/Counters/Increment/` | 200 без тела, счётчики не сохраняются |
| POST | `/v2/signup` | создать отдельный аккаунт LuxBlox и сессию |
| POST | `/v1/login`, `/v2/login` | проверить пароль и создать сессию |
| POST | `/v2/logout` | удалить текущую сессию |
| GET, HEAD | `/v1/users/authenticated` | текущий пользователь или 401 |

POST аккаунтов требует `Content-Type: application/json`. Регистрация принимает
`{"username":"Example","password":"test-password"}`. Вход принимает такую же форму
или `{"ctype":"Username","cvalue":"Example","password":"test-password"}`.
Варианты формы взяты как предварительный контракт: переходы конкретного клиента
на этот API ещё не проверены. Email, телефон, 2FA, captcha, старые аккаунты Korone
и перенос чужих сессий не поддерживаются.

Успешный signup/login: HTTP 200, тело с `userId`, `user` (`id`, `name`, `displayName`),
`isBanned=false`, отдельный Set-Cookie `.ROBLOSECURITY`.
Cookie действует сутки, является host-only и имеет HttpOnly, SameSite=Lax, Secure
(кроме явно включённого loopback-режима). В базе хранится SHA-256 случайного session token.
Это не Roblox/Korone cookie: сервер создаёт и принимает только собственные сессии.

Перед POST аккаунтов сервер проверяет CSRF: если нет подходящего cookie и заголовка,
ответит 403, установит `LUXBLOX-CSRF` и выдаст заголовок `X-CSRF-TOKEN`. Повторить запрос
нужно с сохранённым cookie и этим заголовком. Токен привязан к cookie и становится
недействительным после перезапуска процесса. Такой обмен проверен HTTP-тестами;
автоматический повтор в Android-клиенте предстоит проверить.

Поддержаны `/device/initialize` (случайный browserTrackerId и null appDeviceIdentifier),
обе проверки версии (`data.UpgradeAction=None`), `/v1/enrollments` (`data=[]`)
и `/v1/get-enrollments` (`[]`). Форматы сопоставлены со стартовой машиной клиента
и контроллерами OpenPekora; это не означает, что приложение уже проверено на телефоне.

Unknown endpoints возвращают 404. Не реализованы аватары, список игр, assets,
запуск игровых мест. Их ответы нельзя
выдумывать только ради исчезновения сетевой ошибки — сначала требуется уточнить контракт.

Ограничения прототипа: один процесс, SQLite, 20 попыток аккаунтных операций на адрес
за 10 минут, нет восстановления пароля и полноценного UI. Один и тот же лимит
охватывает регистрацию и вход. Не использовать пароли от других сервисов в тестовых аккаунтах.
