# Persistent account storage (prepared, not activated)

Render Free services discard local filesystem changes on spin-down, restart and redeploy. SQLite in /tmp cannot provide durable accounts. Free Render Postgres expires after 30 days.

Neon offers free PostgreSQL with separately stored data; compute suspension does not clear that storage. Supabase is not required or modified.

Primary references reviewed on 2026-10-29:
- https://render.com/docs/free
- https://neon.com/docs/guides/python
- https://neon.com/docs/introduction/scale-to-zero
- https://www.psycopg.org/psycopg3/docs/basic/usage.html

## Prepared behavior

DATABASE_URL selects PostgreSQL. Local development without it retains SQLite. Password hashing, session tokens and HTTP APIs retain their behavior. PostgreSQL enforces unique usernames ignoring case. Remote connections verify TLS certificates against the system CA bundle. Credentials are neither committed nor logged. Connections close after each transaction, with connection and statement timeouts. Server-side prepared statements are disabled for transaction pooling compatibility.

Set LUXBLOX_REQUIRE_PERSISTENT_DATABASE=1 together with DATABASE_URL on Render. Missing or unreachable external storage stops startup instead of silently creating a SQLite account store. Do not enable the guard on the running service before the database is ready.

The Render native build command must install dependencies:

```sh
python -m pip install -r requirements.txt && python -m unittest discover -s tests -v
```

The Dockerfile installs the same dependency. CI uses disposable PostgreSQL 16 to test account and session survival after Backend recreation, case-insensitive uniqueness/login, binary password hashes, expiry and transaction rollback. Never use production credentials for the CI test URL.

## Activation pending connection

Connect the Neon plugin and create a free project near Render Frankfurt. Transfer its connection string directly into secret Render environment variables; do not expose it in chat, APK, GitHub or logs. Update the build command and set the persistent-storage guard. Coordinate into one deployment where possible. After deployment, register a test account, restart Render once and verify the same account and session work.

The running service has not yet switched to Neon. Existing ephemeral data is not automatically migrated. Preserving any surviving records requires access to their stored salts/hashes; already lost data cannot be reconstructed.

## Menu remains separate

The earlier JavaScriptCallback error disappeared from the supplied log, but AvatarSceneNew.BackPanel then failed. R3 corrects plaintext Lua URL builders and selects an internal avatar scene; it does not prove protected CoreScripts and every native request follow the new paths. Native SignalR WebSocket compatibility remains incomplete. Documentation alone does not establish that the Android menu renders.
