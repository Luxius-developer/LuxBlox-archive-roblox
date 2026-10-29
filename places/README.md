# LuxBlox Starter Obby

Original script-free starter place: one spawn, ten jump platforms and a finish platform. All geometry is anchored. No external assets or scripts are required by the place itself.

Regenerate with `python3 tools/build_starter_place.py`.

`catalog.json` is a local catalog fixture, not a published API response. Place/universe ID 1001 is reserved for testing. Votes and visits start at zero; an unrated game has a null rating. `isPlayable` remains false until an actual compatible game server and join flow exist.

Validation: 20 Python tests passed. Lune 0.11.1 successfully deserialized the XML place into Workspace (13 parts), Players and Lighting. This is format validation, not a Roblox Studio or Android gameplay test.

## Current post-login blocker

The latest phone attempt reached account-info, enrollment and both app policy endpoints with HTTP 200. No catalog or currency requests reached Render afterwards. These logs cannot establish that missing games or currency cause the spinner. HTTP 300 would not fix a response schema or client initialization error.

Capture a fresh Android log while reproducing the spinner, without clearing app data or recreating the account:

```sh
adb logcat -c
adb logcat -v time > ~/luxblox-login-log.txt
```

Open LuxBlox, reproduce the loading screen, wait 20–30 seconds, then press Ctrl+C. Review the log for private information before sharing. We need the native/Lua/network error before deciding the next backend or APK change.

This map-only change intentionally skips Render deployment to preserve the current temporary account.
