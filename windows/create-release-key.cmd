@echo off
rem Runs create-release-key.ps1 for this session only (Windows blocks downloaded scripts by default).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create-release-key.ps1"
pause
