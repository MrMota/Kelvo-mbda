# Lets your phone use Kelvo: private HTTPS through Tailscale, no domain, nothing opened to the internet.
# Needs Tailscale installed and signed in on this PC (https://tailscale.com/download/windows).
# It prints your server address at the end - that is what you type into Kelvo on your phone.
$ErrorActionPreference = 'Stop'
$AppDir = Join-Path $env:LOCALAPPDATA 'Kelvo'
function Fail($msg) { Write-Host ''; Write-Host "Stopped: $msg" -ForegroundColor Red; exit 1 }

# the tailscale command (a fresh install isn't on PATH until a new window is opened)
$Ts = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $Ts) { $Ts = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe' }
if (-not (Test-Path $Ts)) { Fail 'Tailscale is not installed. Get it from https://tailscale.com/download/windows, sign in, then run this again.' }

# 1. this PC's Tailscale name, e.g. desktop-abc123.tail1a2b3c.ts.net
$Status = & $Ts status --json | Out-String | ConvertFrom-Json
if (-not $Status.Self -or -not $Status.Self.DNSName) { Fail 'Tailscale is not signed in. Open Tailscale from the system tray, sign in, then run this again.' }
$Name = $Status.Self.DNSName.TrimEnd('.')
$Address = "https://$Name"
Write-Host "This PC on your tailnet: $Name"

# 2. HTTPS in front of Kelvo, for your tailnet only (serve, NOT funnel)
& $Ts serve --bg 7860
if ($LASTEXITCODE -ne 0) {
    Fail ("tailscale serve did not start. If it printed a link, open it to enable HTTPS certificates for your tailnet " +
          "(admin console > DNS > MagicDNS and HTTPS Certificates), then run this again. " +
          "If it says access denied, run this from a terminal opened with 'Run as administrator'.")
}

# 3. tell Kelvo about its address (saved for your Windows user; used at every start)
[Environment]::SetEnvironmentVariable('KELVO_SECURE_COOKIE', '1', 'User')
[Environment]::SetEnvironmentVariable('KELVO_ALLOWED_ORIGINS', $Address, 'User')
$env:KELVO_SECURE_COOKIE = '1'
$env:KELVO_ALLOWED_ORIGINS = $Address

# 4. restart Kelvo so it picks the settings up
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe' OR Name = 'kelvo.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like '*kelvo*run*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
$Pyw = Join-Path $AppDir 'venv\Scripts\pythonw.exe'
if (-not (Test-Path $Pyw)) { Fail 'Kelvo is not installed yet. Run install.cmd first.' }
Start-Process -FilePath $Pyw -ArgumentList @('-m', 'kelvo.cli', 'run', '--log-file', "`"$(Join-Path $AppDir 'kelvo.log')`"") -WorkingDirectory $AppDir -WindowStyle Hidden

$Up = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "$Address/api/health" | Out-Null; $Up = $true; break } catch { }
}
Write-Host ''
if ($Up) { Write-Host 'Kelvo answers over HTTPS on your tailnet.' -ForegroundColor Green }
else { Write-Host "Kelvo restarted, but $Address did not answer yet (the first HTTPS certificate can take a minute)." -ForegroundColor Yellow }
Write-Host ''
Write-Host 'YOUR SERVER ADDRESS:' -ForegroundColor Cyan
Write-Host "    $Address" -ForegroundColor Cyan
Write-Host ''
Write-Host 'On your phone: install Tailscale, sign in with the same account, then open that address'
Write-Host '(or type it into the Kelvo Android app). Android Chrome: menu > Install app. iPhone Safari: Share > Add to Home Screen.'
Write-Host 'Never run "tailscale funnel" - that would put Kelvo on the public internet.'
