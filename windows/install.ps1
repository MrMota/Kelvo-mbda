# Kelvo for Windows - installs and starts Kelvo without Docker.
# Run by double-clicking install.cmd (in the same folder as the kelvo-*.whl file).
#
# What it does, all inside your user account (no admin needed):
#   1. checks Python 3.10+ and Ollama (offers to install them with winget)
#   2. installs Kelvo into %LOCALAPPDATA%\Kelvo\venv
#   3. creates your Kelvo account (first time only)
#   4. adds Kelvo to your Startup folder so it runs in the background at login
#   5. starts it and opens http://127.0.0.1:7860
# Your data stays in %USERPROFILE%\.kelvo\kelvo.db. Re-run this script to update Kelvo.

$ErrorActionPreference = 'Stop'
$AppDir  = Join-Path $env:LOCALAPPDATA 'Kelvo'
$Venv    = Join-Path $AppDir 'venv'
$LogFile = Join-Path $AppDir 'kelvo.log'
$DataDb  = Join-Path $env:USERPROFILE '.kelvo\kelvo.db'
$Url     = 'http://127.0.0.1:7860'

function Say($msg)  { Write-Host $msg }
function Step($msg) { Write-Host ''; Write-Host "== $msg" -ForegroundColor Cyan }
function Ask($q)    { $a = Read-Host "$q [y/N]"; return ($a -match '^(y|yes)$') }
function Fail($msg) { Write-Host ''; Write-Host "Stopped: $msg" -ForegroundColor Red; exit 1 }

# Returns the command that runs Python 3.10+ as a string array, e.g. @('py','-3') or @('python'), or $null.
function Find-Python {
    $candidates = @('py -3', 'python')
    foreach ($c in $candidates) {
        $parts = $c.Split(' ')
        $exe = $parts[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $pyArgs = @()
        if ($parts.Length -gt 1) { $pyArgs += $parts[1] }
        try {
            $ok = & $exe @pyArgs -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)' 2>$null
            if ("$ok".Trim() -eq '1') { return ,$parts }   # leading comma: keep it an array even with one item
        } catch { }   # e.g. the Microsoft Store "python" placeholder
    }
    return $null
}

# ---------------------------------------------------------------- 0. the package
$Wheel = Get-ChildItem -Path $PSScriptRoot -Filter 'kelvo-*.whl' -ErrorAction SilentlyContinue |
    Sort-Object Name | Select-Object -Last 1
if (-not $Wheel) { Fail "No kelvo-*.whl next to this script. Keep install.cmd, install.ps1 and the .whl file in one folder." }
Say "Kelvo package: $($Wheel.Name)"

# ---------------------------------------------------------------- 1. Python and Ollama
Step 'Python'
$Py = Find-Python
if (-not $Py) {
    Say 'Python 3.10 or newer was not found.'
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (Ask 'Install Python 3.12 now with winget?')) {
        winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
        Fail 'Python was installed. Close this window and double-click install.cmd again.'
    }
    Fail 'Install Python 3.12 from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then run install.cmd again.'
}
$PyArgs = @()
if ($Py.Length -gt 1) { $PyArgs += $Py[1] }
$PyVersion = & $Py[0] @PyArgs -c 'import sys; print(sys.version.split()[0])'
Say "Found Python $PyVersion"

Step 'Ollama'
$OllamaUp = $false
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://127.0.0.1:11434/api/tags' | Out-Null; $OllamaUp = $true } catch { }
if ($OllamaUp) {
    Say 'Ollama is running.'
} elseif (Get-Command ollama -ErrorAction SilentlyContinue) {
    Say 'Ollama is installed but not running. Start it from the Start menu (it uses your NVIDIA GPU automatically).'
} else {
    Say 'Ollama was not found. Kelvo needs it for every model call.'
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (Ask 'Install Ollama now with winget?')) {
        winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
        Say 'Ollama installed. It starts automatically; you may need to open it once from the Start menu.'
    } else {
        Say 'Get it from https://ollama.com/download/windows - you can finish installing Kelvo first.'
    }
}

# ---------------------------------------------------------------- 2. install Kelvo
Step 'Installing Kelvo'
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

# stop a running Kelvo so the files can be replaced
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe' OR Name = 'kelvo.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like '*kelvo*run*' } |
    ForEach-Object { Say "Stopping the running Kelvo (pid $($_.ProcessId))"; Stop-Process -Id $_.ProcessId -Force }

if (-not (Test-Path (Join-Path $Venv 'Scripts\python.exe'))) {
    & $Py[0] @PyArgs -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Fail 'Could not create the Python environment.' }
}
$VenvPy  = Join-Path $Venv 'Scripts\python.exe'
$VenvPyw = Join-Path $Venv 'Scripts\pythonw.exe'
$KelvoExe = Join-Path $Venv 'Scripts\kelvo.exe'
& $VenvPy -m pip install --upgrade --disable-pip-version-check --quiet $Wheel.FullName
if ($LASTEXITCODE -ne 0) { Fail 'pip could not install Kelvo (see the messages above).' }
Say 'Kelvo installed.'

# ---------------------------------------------------------------- 3. your account
Step 'Your account'
if (-not (Test-Path $DataDb)) {
    Say 'Pick the username and password you will sign in with (password: at least 8 characters).'
    & $KelvoExe set-password
    if ($LASTEXITCODE -ne 0) { Fail 'The account was not created. Run install.cmd again.' }
} else {
    Say "Existing data found at $DataDb - keeping your account and flows."
    if (Ask 'Reset your username/password?') { & $KelvoExe set-password }
}

# ---------------------------------------------------------------- 4. start at login
Step 'Start at login'
$Startup = [Environment]::GetFolderPath('Startup')
$Lnk = Join-Path $Startup 'Kelvo.lnk'
$Shell = New-Object -ComObject WScript.Shell
$Sc = $Shell.CreateShortcut($Lnk)
$Sc.TargetPath = $VenvPyw
$Sc.Arguments = "-m kelvo.cli run --log-file `"$LogFile`""
$Sc.WorkingDirectory = $AppDir
$Sc.Description = 'Kelvo (runs in the background)'
$Sc.Save()
Say "Kelvo will start in the background when you sign in to Windows ($Lnk)."

# ---------------------------------------------------------------- 5. start now
Step 'Starting Kelvo'
Start-Process -FilePath $VenvPyw -ArgumentList @('-m', 'kelvo.cli', 'run', '--log-file', "`"$LogFile`"") -WorkingDirectory $AppDir -WindowStyle Hidden
$Up = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "$Url/api/health" | Out-Null; $Up = $true; break } catch { }
}
if (-not $Up) { Fail "Kelvo did not start. Look at the log: $LogFile" }
Say "Kelvo is running at $Url"

if ($OllamaUp -and (Ask 'Download qwen3:30b now (about 19 GB, the recommended agent model for a 32 GB GPU)?')) {
    ollama pull qwen3:30b
    ollama pull nomic-embed-text
}

Start-Process $Url
Write-Host ''
Write-Host 'Done.' -ForegroundColor Green
Say 'Next:'
Say '  1. Sign in, then Settings > Models: pick a default model (one tagged "tools" for agents).'
Say '  2. Install it as an app: Edge  ... menu > Apps > Install Kelvo'
Say '                            Chrome the install icon at the right of the address bar'
Say '  3. Phone: see README.txt ("Use Kelvo on your phone").'
Say "Logs: $LogFile    Data: $DataDb"
