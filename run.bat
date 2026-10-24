@echo off
rem Launch Drift Dreams from this folder.
cd /d "%~dp0"
py drift_dreams.py %*
if errorlevel 1 pause
