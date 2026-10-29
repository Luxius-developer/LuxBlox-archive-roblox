# LuxBlox r5: scope and verification

Package: `com.luxius.luxblox`; visible Android label: `LuxBlox`. Changing package creates a separate app from r4; sign in to the existing server account. Do not delete r4 until device testing passes.

Implemented:
- Original LuxBlox red-brick icon and loading wordmark, Vortix studio / 2010 branding.
- Reviewed launcher PNGs, adaptive/vector launchers, Android loading logos and two OBB logos replaced. Visible Android resource text is rebranded; resource identifiers, Java/JNI class names and third-party license attribution are retained.
- Four reviewed WebView/external-browser URL call sites pass through a helper that rewrites only exact Roblox/Pekora domains and their subdomains to the LuxBlox origin. Other domains and non-HTTP schemes remain unchanged. This does not prove every native network request was rerouted.
- r4's Mobile.rbxl scene repair and six Lua URL-module changes retained; native libraries, TLS verification and CA bundle unchanged.
- Extra account/Robux navigation removed from the WebView pages.
- Private messages implemented for `/my/messages` and `/messages` with persistent storage, CSRF protection, per-user send limits, recipient lookup and automatic polling. JSON endpoints `/luxblox/chat/messages` and `/luxblox/chat/send` enforce session ownership. This is not the legacy native chat protocol or in-game chat.

Checks: APK rebuild, alignment and signature checks; package/label inspection; original-vs-r5 native byte comparison; local API/private-message persistence/isolation tests; isolated Neon schema/SQL delivery test. Android r5 startup, native navigation and chat tab still require a phone test. No device/emulator is attached here.

Not completed: playable native obby, native chat tab, in-game chat, remaining embedded branding and native HTTP failures/slow startup. The existing static map is not labelled playable.

Game-server blocker: OpenPekora `game-server/docker/rccservice.dockerfile` copies an external `rcc-docker/` engine distribution. Its start script launches an external RCC process. Manager scripts alone do not supply that engine. Render exposes one public HTTP/WebSocket port, not the separate public game networking endpoint required by this client. A compatible server runtime and a host with the required inbound game port are still needed. No paid hosting was purchased and no existing account was altered for testing.

Rebuild: decode verified source APK with Apktool 3.0.3; apply tools.patch_client, tools.patch_lua_routes and the pinned tools.patch_avatar_scene; run tools.patch_branding with branding/icon.png and branding/wordmark.png; set apktool.yml versionInfo.versionCode to 971; build and sign with the existing private signing key. Pillow is needed only for the local branding tool, not the hosted API.
