# Android r4: avatar scene mismatch

The observed Lua failure was `BackPanel is not a valid member of Model "ReplicatedStorage.AvatarSceneNew"` in AvatarSceneManager. A failed shared avatar scene initialization can prevent the Lua menu from rendering after Java authentication succeeds. This is a concrete dependency failure, not evidence that a game place or a nonzero Robux balance is required.

The release APK and the unpacked repository contain different Mobile.rbxl resources. The release resource has no object named BackPanel; the repository resource contains BackPanel under AvatarSceneNew. r4 replaces the whole Mobile place with the repository variant. Compatibility of the complete replacement and final menu rendering still require an Android test.

Sources:
- APK: https://github.com/fomeinsaciavel/Pekora-Unofficial-Clients/releases/download/2021/Korone_2021.apk
- Reference OBB: https://raw.githubusercontent.com/fomeinsaciavel/Pekora-Unofficial-Clients/main/2021/assets/main.1.com.roblox.client.obb
- Original APK SHA-256: 05d05b944b86ee0edcd1b62df819999f67490c8c3f82d451c88dbf2ebbca7d3f

Apply the existing Java and Lua routing tools to an Apktool decode, then:

```sh
python3 tools/patch_avatar_scene.py decoded/assets/main.1.com.roblox.client.obb reference.obb --old-sha256 6d8f21eca6b3d78dae4352c3f5f93f51cbb594b215260b5526aa8abe18f1d7c9 --new-sha256 158a859c1e52c11a1964235db51256a801293b5d038371044bfdd4fadab7ed8d
```

Rebuild with Apktool 3.0.3 and sign using the existing private test key. Never commit the signing key or its password. Signature v1/v2/v3 and alignment were verified for the published artifact. The audit JSON records the exact changed OBB entries and signed APK hash. r3 remains available for rollback. No backend change is part of r4.
