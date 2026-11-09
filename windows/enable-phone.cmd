@echo off
rem Runs enable-phone.ps1 for this session only (Windows blocks downloaded scripts by default).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0enable-phone.ps1"
pause
