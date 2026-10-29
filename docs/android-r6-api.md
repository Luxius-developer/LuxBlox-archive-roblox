# Legacy 2021 profile and chat compatibility

This change adds server compatibility for legacy LuaApp requests observed in the client OBB:

- `GET /users/{id}/profile` resolves a LuxBlox account and returns a default avatar URL.
- `GET /thumbnails/v1/users/avatar` and `/thumbnails/v1/games/icons` return the matching static test thumbnails.
- `/chat/v2` routes support authenticated one-to-one conversations, message listing, and sending. Conversation ownership is checked against both participants; writes require the session CSRF token and are rate-limited.
- Conversation data is stored in the same persistent database as accounts. The `chat_conversations` table is created during normal startup for SQLite and PostgreSQL.

These endpoints fill concrete route gaps, but the Android screenshot/phone workflow has not yet been verified against the changed server. The existing chat tab also uses Roblox's SignalR notifications protocol; accepting its negotiation request does not provide a complete SignalR hub. The new `/chat/v2` routes do not, by themselves, make the native chat tab render.

The About page's “FMOD от Firelight Studios” label is a third-party audio-engine acknowledgement, so it remains unchanged. LuxBlox/Vortix Studio branding is applied separately to app artwork.

## Limits

The starter obby remains marked unavailable for native play. This Render service does not include the external RCC game runtime or the separate inbound game-network port needed by this client. A server response or static place thumbnail is not evidence of a playable game session. The current local build environment also has no Android packaging/signing toolchain, so this commit does not produce a new APK or add an in-app “Запустить тестовый плейс” button.

## Verification

`python -m unittest discover -s tests -v` passes the local suite (41 tests, 2 PostgreSQL integration tests skipped when no integration URL is configured). This checks API contracts in the local test server; it does not substitute for phone testing.
