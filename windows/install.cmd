@echo off
rem Runs install.ps1 for this session only (Windows blocks downloaded scripts by default).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
