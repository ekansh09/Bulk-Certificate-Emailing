@echo off
:: Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo This script needs to be run as administrator.
    pause
    exit /b
)

:: Set your project directory
set "TARGET_DIR=C:\Path\To\Your\Project"

:: Change to the directory
cd /d "%TARGET_DIR%"

:: Activate the virtual environment
call venv\Scripts\activate.bat

:: Run the Python app
python app.py

pause
