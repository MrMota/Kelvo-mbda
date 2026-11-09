# Lets your phone use Kelvo over your HOME Wi-Fi - no Tailscale, no domain.
# Kelvo starts listening on your home network; it prints the address to type on your phone.
# Run it again to turn this off.
#
# Limits: works only on the same Wi-Fi as this PC; plain http (fine at home, not on shared networks).
# The Kelvo Android app works with it. Browser "Install app" and the offline page need HTTPS (Tailscale).
$ErrorActionPreference = 'Stop'
$AppDir   = Join-Path $env:LOCALAPPDATA 'Kelvo'
$Pyw      = Join-Path $AppDir 'venv\Scripts\pythonw.exe'
$Port     = 7860
$RuleName = 'Kelvo (home Wi-Fi)'

function Fail($msg) { Write-Host ''; Write-Host "Stopped: $msg" -ForegroundColor Red; exit 1 }
function Step($msg) { Write-Host ''; Write-Host "== $msg" -ForegroundColor Cyan }
function Ask($q)    { $a = Read-Host "$q [y/N]"; return ($a -match '^(y|yes)$') }

if (-not (Test-Path $Pyw)) { Fail 'Kelvo is not installed yet. Run install.cmd first.' }

function Restart-Kelvo {
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe' OR Name = 'kelvo.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine -like '*kelvo*run*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Start-Process -FilePath $Pyw -ArgumentList @('-m', 'kelvo.cli', 'run', '--log-file', "`"$(Join-Path $AppDir 'kelvo.log')`"") `
        -WorkingDirectory $AppDir -WindowStyle Hidden
}

# Runs one firewall command as administrator (Windows shows one permission prompt).
function Invoke-Admin($command) {
    $p = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden `
        -ArgumentList @('-NoProfile', '-Command', $command)
    return ($p.ExitCode -eq 0)
}

# ---------------------------------------------------------------- already on? offer to turn it off
$Current = [Environment]::GetEnvironmentVariable('KELVO_HOST', 'User')
if ($Current -eq '0.0.0.0') {
    Write-Host 'Home Wi-Fi access is ON: Kelvo listens on your home network.'
    if (-not (Ask 'Turn it OFF (Kelvo only on this PC again)?')) { Write-Host 'Left on.'; exit 0 }
    [Environment]::SetEnvironmentVariable('KELVO_HOST', $null, 'User')
    Remove-Item Env:KELVO_HOST -ErrorAction SilentlyContinue
    if (-not (Invoke-Admin "Remove-NetFirewallRule -DisplayName '$RuleName' -ErrorAction SilentlyContinue")) {
        Write-Host "Could not remove the firewall rule '$RuleName' (permission prompt declined?). Remove it in Windows Defender Firewall if you like." -ForegroundColor Yellow
    }
    Restart-Kelvo
    Write-Host ''
    Write-Host 'Home Wi-Fi access is OFF. Kelvo is only on http://127.0.0.1:7860 again.' -ForegroundColor Green
    exit 0
}

# ---------------------------------------------------------------- 1. this PC's home-network address
Step 'Your home network'
$Route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
    Sort-Object -Property RouteMetric, InterfaceMetric | Select-Object -First 1
if (-not $Route) { Fail 'This PC does not seem to be connected to a network.' }
$Ip = (Get-NetIPAddress -InterfaceIndex $Route.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress
if (-not $Ip) { Fail 'Could not find this PC''s address on your home network.' }
$NetProfile = Get-NetConnectionProfile -InterfaceIndex $Route.InterfaceIndex -ErrorAction SilentlyContinue
Write-Host "This PC: $Ip on '$($NetProfile.Name)' ($($NetProfile.InterfaceAlias))"
if ($NetProfile -and $NetProfile.NetworkCategory -eq 'Public') {
    Write-Host ''
    Write-Host 'Windows treats this network as PUBLIC, so it will block your phone.' -ForegroundColor Yellow
    Write-Host 'If this is your home Wi-Fi: Settings > Network & internet > Wi-Fi (or Ethernet) > this network > Network profile type: Private.'
    Write-Host 'Then run this script again. (Kelvo is never opened on Public networks.)'
    exit 1
}

# ---------------------------------------------------------------- 2. firewall: allow the Kelvo port on PRIVATE networks only
Step 'Windows Firewall'
$Rule = "if (-not (Get-NetFirewallRule -DisplayName '$RuleName' -ErrorAction SilentlyContinue)) { " +
        "New-NetFirewallRule -DisplayName '$RuleName' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private | Out-Null }"
Write-Host 'Windows will ask for permission once, to let your phone reach Kelvo on private networks only.'
if (-not (Invoke-Admin $Rule)) { Fail 'The firewall rule was not added (permission prompt declined?). Run this again and choose Yes.' }
Write-Host "Allowed TCP $Port on Private networks ('$RuleName')."

# ---------------------------------------------------------------- 3. listen on the home network, restart
Step 'Restarting Kelvo'
[Environment]::SetEnvironmentVariable('KELVO_HOST', '0.0.0.0', 'User')   # used at every start, incl. Windows sign-in
$env:KELVO_HOST = '0.0.0.0'
Restart-Kelvo

$Url = "http://${Ip}:$Port"
$Up = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "$Url/api/health" | Out-Null; $Up = $true; break } catch { }
}
if (-not $Up) { Fail "Kelvo did not answer on $Url. Look at the log: $(Join-Path $AppDir 'kelvo.log')" }

Write-Host ''
Write-Host 'Kelvo answers on your home network.' -ForegroundColor Green
Write-Host ''
Write-Host 'YOUR PHONE ADDRESS (on this Wi-Fi):' -ForegroundColor Cyan
Write-Host "    $Url" -ForegroundColor Cyan
Write-Host ''
Write-Host 'On your phone: join the same Wi-Fi, open the Kelvo app, enter that address, sign in.'
Write-Host 'Tip: if the address changes after a router restart, reserve this PC''s address in your router'
Write-Host '     (usually called "DHCP reservation"), or just run this script again to see the new one.'
Write-Host 'Run this script again to turn home Wi-Fi access off.'
