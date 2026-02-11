#!/bin/bash
# ============================================
#   Bulk Certificate Generator & Emailer
#   Double-click this file to launch the app
# ============================================

# Change to the directory where this script lives
cd "$(dirname "$0")"

echo "============================================"
echo "  Bulk Certificate Generator & Emailer"
echo "============================================"
echo ""

# Check if Python 3 is available
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "[ERROR] Python is not installed."
    echo "        Install it from https://www.python.org/downloads/"
    echo "        or via Homebrew: brew install python"
    echo ""
    echo "Press any key to exit..."
    read -n 1
    exit 1
fi

echo "[*] Setting up and launching the application..."
echo ""

# Run setup.py which creates venv, installs deps, and launches the app
# (the browser will open automatically once the server is ready)
$PYTHON setup.py

# If we get here, the server was stopped
echo ""
echo "[*] Server stopped."
echo "Press any key to exit..."
read -n 1
