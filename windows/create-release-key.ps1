# Creates your Kelvo APK signing key on THIS PC and walks you through adding the two
# GitHub secrets the release workflow needs. The key never leaves your PC except as the
# encrypted GitHub secret you paste in yourself.
#
#   KELVO_KEYSTORE_BASE64    the key file, as text
#   KELVO_KEYSTORE_PASSWORD  its password (random, 32 characters)
#
# Run once. Back up the folder it creates: every future APK must be signed with this key.
$ErrorActionPreference = 'Stop'
$Repo      = 'MrMota/MBDAflow'
$KeyDir    = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Kelvo signing key'
$Keystore  = Join-Path $KeyDir 'kelvo-release.jks'
$PassFile  = Join-Path $KeyDir 'password.txt'
$B64File   = Join-Path $KeyDir 'keystore-base64.txt'
$SecretUrl = "https://github.com/$Repo/settings/secrets/actions/new"

function Fail($msg) { Write-Host ''; Write-Host "Stopped: $msg" -ForegroundColor Red; exit 1 }
function Step($msg) { Write-Host ''; Write-Host "== $msg" -ForegroundColor Cyan }

# ---------------------------------------------------------------- 1. keytool (comes with Java)
function Find-Keytool {
    $cmd = Get-Command keytool -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $roots = @("$env:ProgramFiles\Microsoft", "$env:ProgramFiles\Eclipse Adoptium", "$env:ProgramFiles\Java", "$env:ProgramFiles\Zulu")
    foreach ($r in $roots) {
        if (-not (Test-Path $r)) { continue }
        $hit = Get-ChildItem -Path $r -Filter keytool.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

Step 'Java keytool'
$Keytool = Find-Keytool
if (-not $Keytool) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Fail 'Install Java first: https://learn.microsoft.com/java/openjdk/download (then run this again).' }
    Write-Host 'Installing Microsoft OpenJDK 17 (needed only for keytool)...'
    winget install -e --id Microsoft.OpenJDK.17 --accept-package-agreements --accept-source-agreements
    $Keytool = Find-Keytool
    if (-not $Keytool) { Fail 'Java was installed. Close this window and run create-release-key.cmd again.' }
}
Write-Host "Using $Keytool"

# ---------------------------------------------------------------- 2. the key
Step 'Signing key'
if (Test-Path $Keystore) {
    Fail ("A key already exists in `"$KeyDir`". Keep using it - a new key would stop updates from installing. " +
          "To re-add the GitHub secrets, use keystore-base64.txt and password.txt from that folder.")
}
New-Item -ItemType Directory -Force -Path $KeyDir | Out-Null

# 32 random letters/digits from the system's cryptographic random generator
$Alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'.ToCharArray()
$Rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
$Bytes = New-Object byte[] 32
$Rng.GetBytes($Bytes)
$Password = -join ($Bytes | ForEach-Object { $Alphabet[$_ % $Alphabet.Length] })

$env:KELVO_KS_PASS = $Password   # passed to keytool by name, so it never appears on a command line
& $Keytool -genkeypair -keystore $Keystore -storetype PKCS12 -alias kelvo -keyalg RSA -keysize 3072 -validity 10000 `
    -dname 'CN=Kelvo, O=Personal' -storepass:env KELVO_KS_PASS -keypass:env KELVO_KS_PASS
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Keystore)) { Remove-Item Env:KELVO_KS_PASS; Fail 'keytool could not create the key (see the message above).' }

Set-Content -Path $PassFile -Value $Password -NoNewline -Encoding ASCII
$B64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($Keystore))
Set-Content -Path $B64File -Value $B64 -NoNewline -Encoding ASCII

$Fingerprint = '(shown in the release notes)'
try {
    $line = & $Keytool -list -v -keystore $Keystore -storepass:env KELVO_KS_PASS -alias kelvo | Select-String 'SHA256:' | Select-Object -First 1
    if ($line) { $Fingerprint = $line.ToString().Split(':', 2)[1].Trim() }
} catch { }
Remove-Item Env:KELVO_KS_PASS
Write-Host "Created $Keystore"
Write-Host "Certificate SHA-256: $Fingerprint"

# ---------------------------------------------------------------- 3. the two GitHub secrets
Step 'GitHub secret 1 of 2: KELVO_KEYSTORE_BASE64'
Set-Clipboard -Value $B64
Start-Process $SecretUrl
Write-Host 'Your browser is opening the "New repository secret" page (sign in to GitHub if asked).'
Write-Host '  Name:   KELVO_KEYSTORE_BASE64'
Write-Host '  Secret: press Ctrl+V  (the key is on your clipboard)'
Write-Host '  Click "Add secret".'
Read-Host 'Press Enter here when it is saved'

Step 'GitHub secret 2 of 2: KELVO_KEYSTORE_PASSWORD'
Set-Clipboard -Value $Password
Start-Process $SecretUrl
Write-Host '  Name:   KELVO_KEYSTORE_PASSWORD'
Write-Host '  Secret: press Ctrl+V  (the password is on your clipboard)'
Write-Host '  Click "Add secret".'
Read-Host 'Press Enter here when it is saved'
Set-Clipboard -Value ' '   # don't leave the password on the clipboard

# ---------------------------------------------------------------- 4. done
Write-Host ''
Write-Host 'Done. Both secrets are set.' -ForegroundColor Green
Write-Host ''
Write-Host 'BACK UP THIS FOLDER (e.g. to a USB stick or your password manager):' -ForegroundColor Yellow
Write-Host "    $KeyDir"
Write-Host '  If you lose it, the next APK cannot update the installed app (you would uninstall/reinstall;'
Write-Host '  your Kelvo data lives on your PC and is not affected). Never commit it to the repository.'
Write-Host ''
Write-Host "Release: https://github.com/$Repo/actions/workflows/release.yml > Run workflow > version 0.2.0"
Write-Host "The release notes will show this certificate fingerprint: $Fingerprint"
Start-Process $KeyDir
