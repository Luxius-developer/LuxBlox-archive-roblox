# R9 APK audit — 2026-10-31

Source: user-provided LuxBlox-r9.apk (119 MiB). Full APK exceeds GitHub's normal 100 MB per-file limit. Preserve binary in a GitHub Release asset or Git LFS, not in Git history.

Embedded OBB: assets/main.1.com.roblox.client.obb (62,423,202 bytes).

Observed LuaApp/Http/Url.lua:
- CHAT_URL = https://luxblox-api.onrender.com/chat/v2
- FRIEND_URL = https://luxblox-api.onrender.com/friends/v1
- USERS_URL = https://luxblox-api.onrender.com/users/v1

Native request contracts observed:
- GET /friends/v1/users/{id}/friends -> expects JSON object with data array; each friend requires id, name, displayName.
- GET /friends/v1/my/friends/count -> expects count.
- POST /chat/v2/start-one-to-one-conversation -> JSON {participantuserId: number} (lowercase u in source).
- POST /chat/v2/send-message -> JSON {conversationId, message, decorators}.

Important friends UI dependency: LuaApp/Thunks/ApiFetchUsersFriends.lua dispatches FetchUserFriendsCompleted only AFTER ApiFetchUsersPresences resolves. Presence request must return userPresences; otherwise friends UI may fail despite valid friends data.

Current server/app.py routes GET /v2/get-user-conversations and /v2/get-messages; server/chat.py conversations have static hasUnreadMessages=false, lastUpdated=now, no latest message details. Compare native consumers before changing shape.

Next: audit exact UsersGetPresence request and response, verify namespace routing, and test response contracts; inspect other legacy hardcoded URLs. No production DB mutation or APK rebuild performed.
