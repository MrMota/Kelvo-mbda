@echo off
rem Runs start-kelvo.ps1 for this session only (Windows blocks downloaded scripts by default).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-kelvo.ps1"
pause
