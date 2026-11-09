# Stops the background Kelvo server. It starts again at your next Windows sign-in.
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe' OR Name = 'kelvo.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like '*kelvo*run*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "Stopped Kelvo (pid $($_.ProcessId))" }
