# Android R9

Package `com.luxius.luxblox`, versionCode 975. R9 is built over the tested R8
client with its URL routing intact, so it installs over R8 without deleting
app data. All mapped legacy HTTP(S) client hosts resolve to
`https://luxblox-api.onrender.com`; individual API namespaces remain in the URL
path. The current API routes supply contract-shaped responses for account,
chat, friends, avatar, catalog, thumbnails, games and votes.

R9 adds the Vortix Studio credit below the preserved FMOD / Firelight Studios
credit in the native information screen. The existing Render WebViews use a
compact blue header and left navigation modeled on the supplied Pekora-era
reference. The original 2021 Android engine and native libraries are not
replaced.

## Build

1. Decode the signed R8 APK with Apktool 3.0.3.
2. Run `python -m tools.patch_native_r9 <decoded-r8> --compiler <luau-compat>`.
3. Set `versionInfo.versionCode` to 975 in `apktool.yml`.
4. Build with `java -jar apktool.jar b <decoded-r8> -o LuxBlox-r9-unsigned.apk`.
5. Align, sign and verify with uber-apk-signer 1.3.0 and the private test key.

The private signing key and its password are stored outside Git. A versionCode
bump permits an in-place update signed by that same key.

## Verification limits

Python API tests and Luau module harnesses check server contracts and client
URL construction. APK package metadata, signature and embedded bundle can be
verified locally. This environment has no Android emulator or attached device;
it cannot prove menu rendering, in-game physics, replication or RCC sessions.
The Render API can publish and list a place, but actual place joining still
requires a compatible game server process.
