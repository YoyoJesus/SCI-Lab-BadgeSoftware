@echo off
cd /d "%~dp0"
py realtime_viewer.py
if errorlevel 1 pause
