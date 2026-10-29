# Android 2021 r2 diagnostic build

The Java `u.Y()` generator now returns `https://luxblox-api.onrender.com/realtime/notifications` directly. It no longer constructs `realtime.<base-host>`. The initial host literal and help URL in this same class also use Render. The reproducible patch adds this override to the existing bootstrap patcher.

APK: LuxBlox-Test-2021-r2.apk. SHA256: 9b155811e08127c6ce6276fd08a408f4109d2b258283a15c10493ca9e5c01a37. Package and manifest version remain dev.luxius.luxblox.test2021 / 970 / 2.477.421716. Signed with the existing LuxBlox test key; v1/v2/v3 signatures and zip alignment verified. The packaged DEX was parsed and Y() contains the exact expected URL. Three patcher tests passed.

This is a diagnostic change, not a confirmed spinner fix. `/realtime/notifications` has no implemented SignalR backend yet. The observed Lua JavaScriptCallback nil error remains unresolved. Native libraries still contain historical Pekora/Roblox domains; see client-endpoint-audit-r2.json. Static string inspection cannot prove every runtime request destination. No native binary strings were overwritten, and no TLS checks were disabled.

No Render deployment was requested for this APK-only change. Existing temporary server accounts should remain valid. Install the APK over the previous test build; data clearing is unnecessary unless separately diagnosed.
