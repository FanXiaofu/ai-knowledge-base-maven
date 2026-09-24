@echo off
chcp 65001 >nul
cd /d "%~dp0"

python ask.py

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start. Please make sure Python is installed and on PATH.
    pause
)
