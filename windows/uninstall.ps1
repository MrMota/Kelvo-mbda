# Removes Kelvo from this PC. Your flows, skills and account stay in %USERPROFILE%\.kelvo
# unless you answer yes to deleting them.
$ErrorActionPreference = 'Stop'
$AppDir = Join-Path $env:LOCALAPPDATA 'Kelvo'
$Data   = Join-Path $env:USERPROFILE '.kelvo'

Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe' OR Name = 'kelvo.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like '*kelvo*run*' } |
    ForEach-Object { Write-Host "Stopping Kelvo (pid $($_.ProcessId))"; Stop-Process -Id $_.ProcessId -Force }

$Lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Kelvo.lnk'
if (Test-Path $Lnk) { Remove-Item $Lnk; Write-Host 'Removed the Startup shortcut.' }
if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir; Write-Host "Removed $AppDir" }

if (Test-Path $Data) {
    $a = Read-Host "Also delete your Kelvo data in $Data (flows, skills, chats, account)? Type DELETE to confirm"
    if ($a -ceq 'DELETE') { Remove-Item -Recurse -Force $Data; Write-Host 'Data deleted.' }
    else { Write-Host "Kept your data in $Data" }
}
Write-Host 'Kelvo is uninstalled. Ollama and Python were left as they are.'
