@echo off
rem Runs enable-home-wifi.ps1 for this session only (Windows blocks downloaded scripts by default).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0enable-home-wifi.ps1"
pause
