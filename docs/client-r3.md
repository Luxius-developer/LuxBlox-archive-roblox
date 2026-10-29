# Android 2021 r3: Lua service URL routing

The latest phone log no longer contains the JavaScriptCallback nil error and reports `onAppReady: Home`. It instead fails in AvatarSceneManager line 72 because runtime AvatarSceneNew has no BackPanel. A separate fetch receives a Render `x-render-routing: no-server` 404.

## Confirmed URL defect

Plaintext `AppTempCommon/LuaApp/Http/Url.lua` splits ContentProvider.BaseUrl at its first dot, assuming a `www` prefix. Given `https://luxblox-api.onrender.com/`, it treats `onrender.com/` as the base domain and builds `https://avatar.onrender.com/`, `https://users.onrender.com/v1`, etc. These hosts do not belong to our service. Other URL builders prepend service subdomains to the full host.

Six reviewed plaintext Lua modules are patched to use the exact Render HTTPS origin with service path namespaces. Examples:

- `/avatar/v1/...`
- `/users/v1/...`
- `/friends/v1/...`
- `/apis/universal-app-configuration/...`

The API recognizes these namespaces while retaining existing Java routes and explicit 404s for unimplemented operations. Basic user profile and empty social lists/counts are supplied. There are no invented friends or followers. This does not implement all Roblox APIs or redirect every native network request.

## Avatar scene

Lune confirms Mobile.rbxl contains `ReplicatedStorage.AvatarSceneNew.BackPanel` (MeshPart) and both model and part are Archivable. Missing resource bytes are therefore not established as the cause. Original upstream AndroidApp enables `FFlagAvatarExperienceUseInternalBackgroundAsset` and `FFlagAvatarExperienceRunSceneFix`; these two settings are now supplied to select the packaged scene and its associated fix. The protected AvatarSceneManager source is not available as plaintext, so successful Android rendering remains unverified.

## Validation and limits

All 24 Python tests passed. All six patched Lua modules executed under Lune with a mocked ContentProvider. Tests exercised table URLs, dynamic site URLs, version/path arguments and vanity-site classification. The OBB has identical entry names and only the six reviewed Lua entries changed; scene models and protected scripts remain unchanged. APK signing and zip alignment are verified using the existing key. See apk-r3-validation.json for the digest.

Server changes require a Render deployment and reset temporary SQLite accounts. Install r3 over r2, then clear app data and register a fresh account after the deployment is live. SignalR remains a limited long-poll implementation; native WebSocket compatibility is unresolved. Main-menu success must be confirmed on the phone, not inferred from unit tests.
