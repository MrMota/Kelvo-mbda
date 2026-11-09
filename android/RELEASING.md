# Releasing Kelvo (signed APK)

Releases are built by GitHub Actions (`.github/workflows/release.yml`) and published on the repository's **Releases** page:

| file | what |
| --- | --- |
| `kelvo-X.Y.Z.apk` | the Android app, signed with **your** release key |
| `kelvo-windows-X.Y.Z.zip` | Kelvo for Windows without Docker (`install.cmd`) |
| `SHA256SUMS.txt` | checksums of both |

Each release runs the backend tests first; nothing is published if they fail.

## One-time: create your signing key (Windows)

**Easiest:** double-click **`windows/create-release-key.cmd`**. It finds (or installs) Java, creates the key with a random 32-character password in `Documents\Kelvo signing key`, then puts each secret on your clipboard in turn and opens GitHub's "New repository secret" page, so you only paste twice. It clears the clipboard at the end and shows the certificate fingerprint. The manual steps below do the same thing.

### Manually

Android only installs an update if it's signed with the **same key** as the installed app. So you create one key, keep it safe forever, and give GitHub a copy as an encrypted secret.

1. Install Java (for `keytool`), in a terminal:
   ```
   winget install Microsoft.OpenJDK.17
   ```
   Open a **new** terminal afterwards.
2. Create the key, in a folder you'll keep (it asks for a password: pick a long one and save it in your password manager):
   ```
   keytool -genkeypair -v -keystore kelvo-release.jks -alias kelvo -keyalg RSA -keysize 3072 -validity 10000 -dname "CN=Kelvo, O=Personal"
   ```
3. Copy it as base64 to the clipboard (PowerShell, in that folder):
   ```
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("$PWD\kelvo-release.jks")) | Set-Clipboard
   ```
4. On GitHub: the repository → **Settings → Secrets and variables → Actions → New repository secret**:
   - `KELVO_KEYSTORE_BASE64`: paste the clipboard
   - `KELVO_KEYSTORE_PASSWORD`: the password from step 2
5. Back up `kelvo-release.jks` and its password somewhere safe (not in the repository). If you lose them, the next APK can't update the installed app: you'd uninstall and reinstall it (your Kelvo data lives on your server, so nothing is lost).

On Linux/macOS, the same `keytool` command works; base64 with `base64 -w0 kelvo-release.jks`.

## Make a release

Either:
- GitHub → **Actions → Release → Run workflow**, enter a version like `0.2.0`; or
- `git tag v0.2.0 && git push origin v0.2.0`

Versions are `MAJOR.MINOR.PATCH` and must go up: the APK's version code is `MAJOR*10000 + MINOR*100 + PATCH`, and Android won't install a lower one over a higher one.

The release notes show the APK's signing-certificate fingerprint; it's the same for every release.

## Installing the release APK

- On your phone, open the release page and download `kelvo-X.Y.Z.apk`, or copy it over. Open it, allow installs from that app once.
- **If you installed the earlier test APK** (sent in chat, signed with a temporary key): uninstall it once first. Android won't replace an app signed with a different key. Your Kelvo data is on your server and is not affected.

## Build locally instead

`bash android/build.sh` (see `android/README.md`). With `KELVO_KEYSTORE=/path/kelvo-release.jks KELVO_KEYSTORE_PASSWORD=… KELVO_VERSION=0.2.0` it signs with your release key exactly like the workflow.
