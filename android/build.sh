#!/usr/bin/env bash
# Build a signed, installable Kelvo APK with Ubuntu/Debian's own Android tools (no Android Studio, no Gradle).
#   sudo apt-get install -y android-sdk-platform-23 aapt dalvik-exchange zipalign apksigner openjdk-17-jdk-headless
#   bash android/build.sh            → android/build/kelvo.apk
#
# Release builds (used by .github/workflows/release.yml):
#   KELVO_VERSION=0.2.0              versionName 0.2.0, versionCode 200 (major*10000 + minor*100 + patch)
#   KELVO_KEYSTORE=/path/to.jks      sign with this keystore instead of ~/.kelvo-android
#   KELVO_KEYSTORE_PASSWORD=...      its password (store and key share it)
#   KELVO_KEY_ALIAS=kelvo            key alias (default kelvo)
# Signing key: never stored in the repo; it lives in ~/.kelvo-android/ (created on first build).
# Keep that folder: an update to the app must be signed with the same key, or Android asks you to uninstall first.
set -euo pipefail
cd "$(dirname "$0")"

ANDROID_JAR="${ANDROID_JAR:-/usr/lib/android-sdk/platforms/android-23/android.jar}"
KEY_DIR="${KELVO_KEY_DIR:-$HOME/.kelvo-android}"
KEYSTORE="${KELVO_KEYSTORE:-$KEY_DIR/kelvo-release.jks}"
PASSFILE="$KEY_DIR/keystore-password"
ALIAS="${KELVO_KEY_ALIAS:-kelvo}"
VERSION="${KELVO_VERSION:-}"
OUT=build

for tool in aapt dalvik-exchange zipalign apksigner javac keytool; do
  command -v "$tool" >/dev/null || { echo "Missing '$tool'. Install: sudo apt-get install -y android-sdk-platform-23 aapt dalvik-exchange zipalign apksigner openjdk-17-jdk-headless" >&2; exit 1; }
done
[ -f "$ANDROID_JAR" ] || { echo "Missing $ANDROID_JAR (package android-sdk-platform-23)." >&2; exit 1; }

rm -rf "$OUT" && mkdir -p "$OUT/gen" "$OUT/classes"

# Version: from KELVO_VERSION (x.y.z) into a copy of the manifest; the checked-in manifest stays as is.
MANIFEST="$OUT/AndroidManifest.xml"
cp AndroidManifest.xml "$MANIFEST"
if [ -n "$VERSION" ]; then
  [[ "$VERSION" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]] || { echo "KELVO_VERSION must look like 1.2.3 (got '$VERSION')" >&2; exit 1; }
  CODE=$(( BASH_REMATCH[1] * 10000 + BASH_REMATCH[2] * 100 + BASH_REMATCH[3] ))
  [ "$CODE" -gt 0 ] || { echo "KELVO_VERSION must be above 0.0.0" >&2; exit 1; }
  sed -i -e "s/android:versionCode=\"[0-9]*\"/android:versionCode=\"$CODE\"/" \
         -e "s/android:versionName=\"[^\"]*\"/android:versionName=\"$VERSION\"/" "$MANIFEST"
  echo "version $VERSION (code $CODE)"
fi

echo "1/6 resources → R.java"
aapt package -f -m -J "$OUT/gen" -M "$MANIFEST" -S res -I "$ANDROID_JAR"

echo "2/6 compile Java"
javac -source 8 -target 8 -bootclasspath "$ANDROID_JAR" -Xlint:-options -encoding UTF-8 \
  -d "$OUT/classes" $(find src "$OUT/gen" -name '*.java')

echo "3/6 convert to Android bytecode"
dalvik-exchange --dex --min-sdk-version=24 --output="$OUT/classes.dex" "$OUT/classes"

echo "4/6 package"
aapt package -f -M "$MANIFEST" -S res -I "$ANDROID_JAR" -F "$OUT/kelvo-unaligned.apk"
(cd "$OUT" && aapt add -k kelvo-unaligned.apk classes.dex >/dev/null)
zipalign -f -p 4 "$OUT/kelvo-unaligned.apk" "$OUT/kelvo-aligned.apk"

echo "5/6 signing key"
if [ -n "${KELVO_KEYSTORE_PASSWORD:-}" ]; then
  [ -f "$KEYSTORE" ] || { echo "KELVO_KEYSTORE_PASSWORD is set but there is no keystore at $KEYSTORE" >&2; exit 1; }
  KS_PASS="env:KELVO_KEYSTORE_PASSWORD"
elif [ ! -f "$KEYSTORE" ]; then
  mkdir -p "$KEY_DIR" && chmod 700 "$KEY_DIR"
  head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$PASSFILE" && chmod 600 "$PASSFILE"
  keytool -genkeypair -keystore "$KEYSTORE" -storepass:file "$PASSFILE" -keypass:file "$PASSFILE" \
    -alias kelvo -keyalg RSA -keysize 3072 -validity 10000 -dname "CN=Kelvo, O=Personal" >/dev/null 2>&1
  chmod 600 "$KEYSTORE"
  echo "    created $KEYSTORE (keep this folder for future updates)"
fi
KS_PASS="${KS_PASS:-file:$PASSFILE}"

echo "6/6 sign + verify"
apksigner sign --ks "$KEYSTORE" --ks-pass "$KS_PASS" --ks-key-alias "$ALIAS" \
  --min-sdk-version 24 --out "$OUT/kelvo.apk" "$OUT/kelvo-aligned.apk"
apksigner verify --min-sdk-version 24 "$OUT/kelvo.apk"
rm -f "$OUT/kelvo-unaligned.apk" "$OUT/kelvo-aligned.apk" "$OUT"/kelvo.apk.idsig
echo "Built $(pwd)/$OUT/kelvo.apk ($(du -k "$OUT/kelvo.apk" | cut -f1) KB)"
