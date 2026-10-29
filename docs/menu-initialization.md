# Post-login initialization: first backend correction

Evidence from Android 2021 and the latest r2 server logs:

- `DualSurfaceApp::initializeLuaAppWithLoggedInUser` sees userId 1; account authentication succeeds.
- `UniversalAppRobloxHybridEventReceiver:75` fails while rendering with `attempt to index nil with 'JavaScriptCallback'`.
- The original AndroidApp configuration enables `FFlagEnableJavascriptHybrid2` and `FFlagDatamodelServicesConnectionFix2`. Our initial minimal response omitted both. Their names also exist in the client/native configuration; Java forwards fetched application settings into `nativeInitClientSettings`. Enabling these is a targeted hypothesis for the missing bridge, not a demonstrated runtime fix.
- `DFFlagUseBaseUrlNotHardcodedUrl` is enabled in the original configuration and in this experiment to favor the supplied base URL. It does not prove that every native endpoint is rewritten.
- Java `s/g.smali` uses `JSONObject.optInt` for `RobuxBalance`, so an absent field defaults to zero. No evidence makes this the cause of the Lua exception. We now explicitly return zero at `/my/balance`, `/v1/user/currency`, and in the classic account-info fields.
- r2 reaches `/realtime/notifications/signalr/negotiate` repeatedly and gets 404. This is now an implemented legacy SignalR 1.2–1.5 handshake, with signed, expiring tokens bound to the authenticated user and only long polling advertised/accepted. Connect, reconnect, poll, start and abort have protocol-shaped responses. Polls wait two seconds to avoid a tight empty loop. There is no notification delivery, hub invocation API, WebSocket or SSE transport. This is a compatibility subset, not a full SignalR service.

Primary protocol source reviewed: https://github.com/SignalR/SignalR/blob/main/src/Microsoft.AspNet.SignalR.Core/PersistentConnection.cs (negotiation payload and start response). Local upstream configuration: `Roblox/Roblox.Libraries/Json/AndroidApp.json` at OpenPekora commit 54c25c704a3c2cbecf5d3c79b823a43e492b30bf. Core scripts inside the client's DataModelPatch use protected source type 0x1d; ordinary Lune parsing cannot expose their Lua source. The exact expression at receiver line 75 has therefore not been recovered.

Validation: 23 tests, including authenticated zero balance, complete long-poll handshake, malformed tokens, unsupported protocol and cross-user token rejection. Android end-to-end success remains pending.

This backend commit triggers one Render deployment and resets temporary SQLite accounts. Retest with the existing r2 APK after the deploy becomes live, register a fresh account, and capture a new log if the menu still stalls. Do not represent local HTTP tests as proof that the Android menu works.
