# Android r6 artwork refresh

Package: `com.luxius.luxblox`, versionCode 972. Built from the signed r5 APK with Apktool 3.0.3 and the `--artwork-only` mode in tools/patch_branding.py, then aligned/signed/verified with uber-apk-signer 1.3.0 and the existing private test key. The signing key is never committed.

The launcher and two reviewed loading images now use the muted LuxBlox/Vortix Studio artwork with transparent loading backgrounds. Firelight Studios remains credited for FMOD.

The r5 classes.dex and all ten native libraries were copied unchanged. OBB entries changed only for the two reviewed logo images. The package was inspected with aapt2; v1/v2/v3 signatures and alignment were verified. The verifier emits 49 v1 warnings about unsigned META-INF dependency metadata; v2/v3 verification passes. See android-r6-audit.json for exact SHA256 and the preserved files.

This is an artwork update. Main-menu behavior, native chat, in-game chat and native obby launch have not been confirmed on a device. No native test-place button is included. No RCC game runtime was added.

The repository's 30 Actions runs through commit a310ab4 are backend checks only. Earlier APKs were locally built and published through GitHub Releases; GitHub Actions was not the APK builder. The local tools were restored by downloading the official release jars.
