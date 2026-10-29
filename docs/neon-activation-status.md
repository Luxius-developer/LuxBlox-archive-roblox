# Neon activation status — 2026-10-29

Created a project named LuxBlox Accounts under the connected Sans Free organization, PostgreSQL 16, AWS Frankfurt, fixed 0.25 CU. Project: mute-thunder-55773356. Production branch: br-dark-wind-b9h9ppmf. Database: luxblox. The users/sessions schema and indexes from server/postgres.py were initialized and verified through the Neon connection. Transaction pooling is enabled for the app's supplied pooled connection URL.

DATABASE_URL and LUXBLOX_REQUIRE_PERSISTENT_DATABASE=1 were merged into Render's existing environment through the connector. Connection values were not committed or printed. This tool automatically triggered deployment dep-dbhks5vf3r2c73d5u5v0 from df4139b72acfba5557b46bd6d1678c75799d9e7c. It reached update_failed; PostgreSQL is NOT active in the public service yet. Render retained/returned to the older running application.

The existing Render build command remains `python -m unittest discover -s tests -v`; it does not install the new requirements. It must become:

```sh
python -m pip install -r requirements.txt && python -m unittest discover -s tests -v
```

The installed Render connector does not expose updating an existing service's build command. Dashboard sign-in was attempted using the secure browser flow but declined. No additional credential requests were made. The next step is to change Build Command under the service's Settings and deploy the latest commit. Do not replace or reveal the already-saved DATABASE_URL.

Public service: https://dashboard.render.com/web/srv-dbhhghs9v7es73avjcd0

Acceptance still pending: after the corrected deployment becomes live, create an HTTPS test account, verify login and session, restart Render, and verify the same credentials and session again. CI tested PostgreSQL persistence across Backend recreation, but this does not replace the actual Render restart check.

A local direct-Postgres probe could not resolve the Neon host from the execution environment. This is not evidence that the hosted database or Render cannot reach it. Schema checks through the Neon connector succeeded. No new live persistence claim is made.

Existing ephemeral accounts were not migrated. Their current survival cannot be inferred from the failed deployment. The previous SQLite deployment remains subject to loss on spin-down/restart until the service actually switches to PostgreSQL.
