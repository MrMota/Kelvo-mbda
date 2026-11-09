@echo off
rem Runs stop-kelvo.ps1 for this session only (Windows blocks downloaded scripts by default).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-kelvo.ps1"
pause
