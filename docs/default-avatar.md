# Default avatar compatibility API

Adds GET /avatar/v1/avatar and /avatar/v1/users/{id}/avatar with R6, classic body colors, neutral scales and no worn external assets. Own avatar requires a session; public avatar verifies that the user exists. Adds /avatar/v1/avatar/metadata. This is a read-only test avatar, not an avatar editor, thumbnails service or 3D asset delivery server.

Validated locally with authentication, existing/missing users and schema checks. Main-menu rendering remains unverified. The historical Client Tracker snapshot 2a66531e2d30266e99083e4278cba12830cf2e96 contains supporting Lua packages but no AvatarSceneManager source; it cannot settle the protected script's BackPanel failure. No speculative feature flags were changed.
