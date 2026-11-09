# Kelvo for Android

A small app (≈40 KB) that opens **your** Kelvo server full-screen. Kelvo itself keeps running on your GPU machine; the phone reaches it over Tailscale.

## Install

1. Copy `kelvo.apk` to your phone and open it. Android asks once to allow installs from that app (Files, Chrome, Drive…): allow it.
2. Turn on **Tailscale** on the phone.
3. Open **Kelvo**, enter your server address, e.g. `https://my-pc.my-tailnet.ts.net` (`tailscale serve status` on the server shows it), tap **Connect**, sign in.

The address is remembered. To change it: Kelvo → Settings → Account → **Change server address**, or tap **Change server address** on the "Can't reach Kelvo" screen.

## What the app does

- Loads only your server; links to other sites open in your browser.
- Keeps you signed in (the session cookie is saved when you leave the app).
- File import (flows, SKILL.md) uses the Android file picker; exports open Android's **Save to…** picker.
- If the server can't be reached (Tailscale off, server down), shows a retry screen instead of a blank page.
- Refuses invalid HTTPS certificates. Plain `http://` addresses (e.g. `http://100.x.y.z:7860`) are allowed for your tailnet, but `https://….ts.net` is recommended.

Kelvo's features and updates come from your server, so the app itself rarely needs updating.

## Releases

Signed release APKs are published on the repository's **Releases** page by GitHub Actions. One-time key setup and how to cut a release: **`RELEASING.md`**.

## Build it yourself (Ubuntu/Debian)

```bash
sudo apt-get install -y android-sdk-platform-23 aapt dalvik-exchange zipalign apksigner openjdk-17-jdk-headless
bash android/build.sh        # → android/build/kelvo.apk
```

No Android Studio or Gradle. The signing key is created on the first build in `~/.kelvo-android/` (never in the repo). Keep that folder: installing a newer build over the old app needs the same key; otherwise uninstall the old app first (your Kelvo data lives on the server, so nothing is lost).

Compiled against Android 6 (API 23) from Ubuntu's packages, `minSdk 24` (Android 7+), `targetSdk 34`. Signed with APK Signature Scheme v2 + v3.
