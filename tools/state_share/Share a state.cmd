@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0StateShare.ps1" -Mode Export -Path "%~1"
if errorlevel 1 pause
