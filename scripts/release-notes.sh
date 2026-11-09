#!/usr/bin/env bash
# Writes the release notes for Kelvo VERSION from the files in DIR (kelvo-VERSION.apk,
# kelvo-windows-VERSION.zip): install steps, the APK signing fingerprint and SHA-256 checksums.
# Used by .github/workflows/release.yml (new releases) and release-notes.yml (refresh existing ones).
#   bash scripts/release-notes.sh 0.2.1 dist > notes.md
set -euo pipefail
V="$1"; DIR="$2"
APK="kelvo-$V.apk"; WIN="kelvo-windows-$V.zip"
[ -f "$DIR/$APK" ] && [ -f "$DIR/$WIN" ] || { echo "missing $DIR/$APK or $DIR/$WIN" >&2; exit 1; }
SIGNER=$(apksigner verify --print-certs "$DIR/$APK" | grep -m1 'SHA-256' | sed 's/.*: //')
[ -n "$SIGNER" ] || { echo "could not read the APK signing certificate" >&2; exit 1; }
SUMS=$(cd "$DIR" && sha256sum "$APK" "$WIN")

cat <<NOTES
## Android app

1. On your phone, download **\`$APK\`** below and open it. Allow installs from your browser once.
2. Open **Kelvo** and enter your Kelvo server's address. Pick one way to connect:
   - **At home, same Wi-Fi (no Tailscale):** on your PC run \`enable-home-wifi.cmd\`; it prints an address like \`http://192.168.1.50:7860\`.
   - **Anywhere, with Tailscale:** turn Tailscale on (on the PC and the phone); on your PC run \`enable-phone.cmd\`; it prints an address like \`https://my-pc.my-tailnet.ts.net\`.
3. Sign in.

Updates install over the previous version: every release is signed with the same key. If you installed a test APK sent in chat, uninstall it once first.

## Windows (no Docker)

Unzip **\`$WIN\`** and double-click \`install.cmd\`. To update, run it again: your flows, skills and account are kept.
Phone access: \`enable-home-wifi.cmd\` (home Wi-Fi only) and/or \`enable-phone.cmd\` (anywhere, via Tailscale). See \`README.txt\` in the zip.

## Verify

APK signing certificate (SHA-256): \`$SIGNER\`

\`\`\`
$SUMS
\`\`\`
NOTES
