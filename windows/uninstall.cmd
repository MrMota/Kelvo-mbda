@echo off
rem Runs uninstall.ps1 for this session only (Windows blocks downloaded scripts by default).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
pause
