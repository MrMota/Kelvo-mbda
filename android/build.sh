#!/usr/bin/env bash
# Build a signed, installable Kelvo APK with Ubuntu/Debian's own Android tools (no Android Studio, no Gradle).
#   sudo apt-get install -y android-sdk-platform-23 aapt dalvik-exchange zipalign apksigner openjdk-17-jdk-headless
#   bash android/build.sh            → android/build/kelvo.apk
# Signing key: never stored in the repo; it lives in ~/.kelvo-android/ (created on first build).
# Keep that folder: an update to the app must be signed with the same key, or Android asks you to uninstall first.
set -euo pipefail
cd "$(dirname "$0")"

ANDROID_JAR="${ANDROID_JAR:-/usr/lib/android-sdk/platforms/android-23/android.jar}"
KEY_DIR="${KELVO_KEY_DIR:-$HOME/.kelvo-android}"
KEYSTORE="$KEY_DIR/kelvo-release.jks"
PASSFILE="$KEY_DIR/keystore-password"
OUT=build

for tool in aapt dalvik-exchange zipalign apksigner javac keytool; do
  command -v "$tool" >/dev/null || { echo "Missing '$tool'. Install: sudo apt-get install -y android-sdk-platform-23 aapt dalvik-exchange zipalign apksigner openjdk-17-jdk-headless" >&2; exit 1; }
done
[ -f "$ANDROID_JAR" ] || { echo "Missing $ANDROID_JAR (package android-sdk-platform-23)." >&2; exit 1; }

rm -rf "$OUT" && mkdir -p "$OUT/gen" "$OUT/classes"

echo "1/6 resources → R.java"
aapt package -f -m -J "$OUT/gen" -M AndroidManifest.xml -S res -I "$ANDROID_JAR"

echo "2/6 compile Java"
javac -source 8 -target 8 -bootclasspath "$ANDROID_JAR" -Xlint:-options -encoding UTF-8 \
  -d "$OUT/classes" $(find src "$OUT/gen" -name '*.java')

echo "3/6 convert to Android bytecode"
dalvik-exchange --dex --min-sdk-version=24 --output="$OUT/classes.dex" "$OUT/classes"

echo "4/6 package"
aapt package -f -M AndroidManifest.xml -S res -I "$ANDROID_JAR" -F "$OUT/kelvo-unaligned.apk"
(cd "$OUT" && aapt add -k kelvo-unaligned.apk classes.dex >/dev/null)
zipalign -f -p 4 "$OUT/kelvo-unaligned.apk" "$OUT/kelvo-aligned.apk"

echo "5/6 signing key"
if [ ! -f "$KEYSTORE" ]; then
  mkdir -p "$KEY_DIR" && chmod 700 "$KEY_DIR"
  head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$PASSFILE" && chmod 600 "$PASSFILE"
  keytool -genkeypair -keystore "$KEYSTORE" -storepass:file "$PASSFILE" -keypass:file "$PASSFILE" \
    -alias kelvo -keyalg RSA -keysize 3072 -validity 10000 -dname "CN=Kelvo, O=Personal" >/dev/null 2>&1
  chmod 600 "$KEYSTORE"
  echo "    created $KEYSTORE (keep this folder for future updates)"
fi

echo "6/6 sign + verify"
apksigner sign --ks "$KEYSTORE" --ks-pass "file:$PASSFILE" --ks-key-alias kelvo \
  --min-sdk-version 24 --out "$OUT/kelvo.apk" "$OUT/kelvo-aligned.apk"
apksigner verify --min-sdk-version 24 "$OUT/kelvo.apk"
rm -f "$OUT/kelvo-unaligned.apk" "$OUT/kelvo-aligned.apk" "$OUT"/kelvo.apk.idsig
echo "Built $(pwd)/$OUT/kelvo.apk ($(du -k "$OUT/kelvo.apk" | cut -f1) KB)"
