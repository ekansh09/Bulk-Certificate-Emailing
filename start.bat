@echo off
title Bulk Certificate Emailer
cd /d "%~dp0"

echo ============================================
echo   Bulk Certificate Generator ^& Emailer
echo ============================================
echo.

:: Check if Python is installed
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Download it from https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [*] Setting up and launching the application...
echo.

:: Run setup.py which creates venv, installs deps, and launches the app
:: (the browser will open automatically once the server is ready)
python setup.py

:: If we get here, the server was stopped
echo.
echo [*] Server stopped.
pause
