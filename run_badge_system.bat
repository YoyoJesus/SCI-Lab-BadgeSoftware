@echo off
REM Batch file to run the PowerShell script without execution policy issues
echo Starting Voice Badge System...
powershell.exe -ExecutionPolicy Bypass -File "%~dp0start_voice_badge_system.ps1" %*