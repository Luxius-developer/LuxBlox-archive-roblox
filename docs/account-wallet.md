# Test wallet and account WebViews

The existing Android r4 opens `/upgrades/robux` and `/my/account`. Both now serve Russian pages with the classic light/blue client style. No new APK is needed for these pages.

- Free test packs: 80, 400, 800, 1700 Robux. They are local LuxBlox currency, with no payment integration.
- Every form carries a session-bound CSRF token. Every grant has a per-user idempotency key; submitting it again does not credit twice.
- Display name is free. Username changes cost 500 and require the current password; uniqueness and debit commit or roll back together.
- Password changes require the current password and confirmation. Passwords are scrypt-hashed with new random salt. Other sessions are revoked; the current session stays active.
- Two additive, idempotent tables are defined in `server/accounts.py:initialize`: account_profiles and wallet_grants. Existing user IDs and sessions remain intact.
- Balance is read from persistent storage for the WebView, `/my/balance`, `/economy/v1/user/currency` and Java `/users/account-info`. Native titles may refresh only after closing/reopening the dialog or relaunching the client.

SQLite tests cover concurrent/replayed grants, persistence across Backend recreation, failed username edits without a debit, successful debit, display-name persistence, password replacement/session revocation, HTML escaping, HTTP CSRF rejection and API balance consistency. PostgreSQL DDL, RETURNING, replay rejection and a uniqueness-error transaction rollback were checked on isolated Neon branch br-morning-dream-b9awoag3. Full direct-connection Python PostgreSQL integration was unavailable from scratch due to DNS resolution; the connector SQL checks are not a substitute for the live HTTP smoke test.

Remaining: Lua Home/game/avatar/chat requests are still absent from observed Render logs. This wallet/account change does not claim to solve that client networking problem or enable game joining.

Live HTTPS smoke on 2026-10-29 passed: signup, wallet HTML, missing-CSRF rejection, 800 credit, replay without double credit, display-name edit, wrong-current-password rejection, username change with balance 300, password change, retained current session and a fresh client login using the new credentials with balance still 300. Tests used a separate QA account.
