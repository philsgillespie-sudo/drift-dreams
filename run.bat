@echo off
rem Launch Cops & Robbers from this folder.
cd /d "%~dp0"
py drift_dreams.py %*
if errorlevel 1 pause
