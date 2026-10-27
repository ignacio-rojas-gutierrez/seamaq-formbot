@echo off
REM Double-click launcher for setup.ps1 (bypasses the PowerShell execution policy for this run only).
REM Extra arguments are passed along, e.g.:  setup.bat -InstallTesseract
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
pause
