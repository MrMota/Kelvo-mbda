# Starts Kelvo in the background (if it isn't running) and opens it.
$AppDir = Join-Path $env:LOCALAPPDATA 'Kelvo'
$Pyw = Join-Path $AppDir 'venv\Scripts\pythonw.exe'
if (-not (Test-Path $Pyw)) { Write-Host 'Kelvo is not installed. Run install.cmd first.'; exit 1 }
$running = Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" | Where-Object { $_.CommandLine -like '*kelvo*run*' }
if (-not $running) {
    Start-Process -FilePath $Pyw -ArgumentList @('-m', 'kelvo.cli', 'run', '--log-file', "`"$(Join-Path $AppDir 'kelvo.log')`"") -WorkingDirectory $AppDir -WindowStyle Hidden
    Start-Sleep -Seconds 2
}
Start-Process 'http://127.0.0.1:7860'
