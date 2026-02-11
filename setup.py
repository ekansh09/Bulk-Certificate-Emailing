#!/usr/bin/env python3
"""
Setup & Bootstrap Script — Bulk Certificate Emailer

Works on both macOS and Windows.
Creates a virtual environment, installs dependencies, verifies
permissions, and launches the web application.

Usage:
    python setup.py          # Full setup + launch
    python setup.py --check  # Health check only (no launch)

Author: Ekansh Chauhan
"""

import os
import sys
import subprocess
import platform
import shutil
import argparse
import json

# ── Constants ───────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(BASE_DIR, '.venv')
REQ_FILE = os.path.join(BASE_DIR, 'requirements.txt')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

IS_WIN = platform.system() == 'Windows'
PYTHON = sys.executable

if IS_WIN:
    VENV_PYTHON = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
    VENV_PIP = os.path.join(VENV_DIR, 'Scripts', 'pip.exe')
else:
    VENV_PYTHON = os.path.join(VENV_DIR, 'bin', 'python')
    VENV_PIP = os.path.join(VENV_DIR, 'bin', 'pip')

REQUIRED_PACKAGES = [
    'flask', 'pandas', 'openpyxl', 'docxtpl',
    'docx2pdf', 'mammoth', 'retrying',
]

# ── Helpers ─────────────────────────────────────────────────────────

class C:
    """ANSI colors (no-op on Windows if not supported)."""
    if IS_WIN:
        os.system('')  # Enable ANSI on Windows 10+

    RESET  = '\033[0m'
    BOLD   = '\033[1m'
    RED    = '\033[91m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    CYAN   = '\033[96m'
    DIM    = '\033[2m'


def log(icon, msg, color=C.RESET):
    print(f"  {color}{icon}{C.RESET}  {msg}")


def log_ok(msg):
    log('✓', msg, C.GREEN)


def log_warn(msg):
    log('!', msg, C.YELLOW)


def log_fail(msg):
    log('✗', msg, C.RED)


def log_info(msg):
    log('→', msg, C.CYAN)


def header(text):
    w = 60
    print()
    print(f"{C.BOLD}{'═' * w}{C.RESET}")
    print(f"{C.BOLD}  {text}{C.RESET}")
    print(f"{C.BOLD}{'═' * w}{C.RESET}")
    print()


def run(cmd, capture=False, check=True):
    """Run a subprocess command."""
    result = subprocess.run(
        cmd, capture_output=capture, text=True,
        check=check, cwd=BASE_DIR,
    )
    return result


# ── Check Functions ─────────────────────────────────────────────────

def check_python_version():
    """Ensure Python >= 3.8."""
    v = sys.version_info
    if v >= (3, 8):
        log_ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    log_fail(f"Python {v.major}.{v.minor}.{v.micro} — need >= 3.8")
    return False


def check_venv_exists():
    """Check if virtual environment directory exists."""
    exists = os.path.isfile(VENV_PYTHON)
    if exists:
        log_ok(f"Virtual environment found: {VENV_DIR}")
    else:
        log_warn(f"Virtual environment not found at {VENV_DIR}")
    return exists


def create_venv():
    """Create a virtual environment."""
    log_info(f"Creating virtual environment at {VENV_DIR}…")
    try:
        run([PYTHON, '-m', 'venv', VENV_DIR])
        log_ok("Virtual environment created")
        return True
    except subprocess.CalledProcessError as e:
        log_fail(f"Failed to create venv: {e}")
        print()
        log_info("Try manually:")
        log_info(f"  {PYTHON} -m venv {VENV_DIR}")
        return False


def check_packages():
    """Check which required packages are installed in the venv."""
    try:
        result = run(
            [VENV_PIP, 'list', '--format=json'],
            capture=True, check=True,
        )
        installed = {
            p['name'].lower()
            for p in json.loads(result.stdout)
        }
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        installed = set()

    missing = []
    for pkg in REQUIRED_PACKAGES:
        name = pkg.lower()
        if name in installed:
            log_ok(f"  {pkg}")
        else:
            log_fail(f"  {pkg} — not installed")
            missing.append(pkg)
    return missing


def install_packages():
    """Install all requirements from requirements.txt."""
    log_info("Installing packages from requirements.txt…")
    try:
        run([VENV_PIP, 'install', '--upgrade', 'pip'], capture=True)
        run([VENV_PIP, 'install', '-r', REQ_FILE])
        log_ok("All packages installed")
        return True
    except subprocess.CalledProcessError as e:
        log_fail(f"pip install failed: {e}")
        return False


def check_write_permissions():
    """Check write access to key directories."""
    dirs_to_check = [
        ('App directory', BASE_DIR),
        ('Uploads', os.path.join(BASE_DIR, 'uploads')),
        ('Certificates', os.path.join(BASE_DIR, 'certificates')),
    ]
    all_ok = True
    for label, d in dirs_to_check:
        os.makedirs(d, exist_ok=True)
        test_file = os.path.join(d, '.write_test')
        try:
            with open(test_file, 'w') as f:
                f.write('ok')
            os.remove(test_file)
            log_ok(f"{label}: writable")
        except (PermissionError, OSError) as e:
            log_fail(f"{label}: NOT writable — {e}")
            all_ok = False
            if IS_WIN:
                log_info("  Try running as Administrator, or check folder permissions")
            else:
                log_info(f"  Try: chmod -R u+rw \"{d}\"")
    return all_ok


def check_docx2pdf_backend():
    """Check if docx2pdf conversion backend is available."""
    if IS_WIN:
        # Needs Microsoft Word installed
        try:
            import win32com.client
            word = win32com.client.Dispatch('Word.Application')
            word.Quit()
            log_ok("Microsoft Word available (docx→pdf conversion)")
            return True
        except Exception:
            log_warn("Microsoft Word not detected — PDF conversion may fail")
            log_info("  Install Microsoft Word, or use LibreOffice as a backend")
            return False
    else:
        # macOS/Linux: needs LibreOffice or Word
        if shutil.which('libreoffice') or shutil.which('soffice'):
            log_ok("LibreOffice available (docx→pdf conversion)")
            return True
        # Check for macOS Word
        word_path = '/Applications/Microsoft Word.app'
        if os.path.exists(word_path):
            log_ok("Microsoft Word available (docx→pdf conversion)")
            return True
        log_warn("No PDF converter found (LibreOffice or Word needed)")
        if platform.system() == 'Darwin':
            log_info("  Install: brew install --cask libreoffice")
        else:
            log_info("  Install: sudo apt install libreoffice")
        return False


def check_admin():
    """Check if running with elevated privileges (informational)."""
    if IS_WIN:
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False
        if is_admin:
            log_ok("Running as Administrator")
        else:
            log_info("Not running as Administrator (usually not needed)")
        return is_admin
    else:
        is_root = os.geteuid() == 0
        if is_root:
            log_warn("Running as root — not recommended, use a regular user")
        else:
            log_ok(f"Running as user: {os.environ.get('USER', 'unknown')}")
        return True


# ── Main ────────────────────────────────────────────────────────────

def health_check():
    """Run all checks and return True if everything is good."""
    header("System Check")
    results = {}

    print(f"  {C.DIM}Platform: {platform.system()} {platform.release()}{C.RESET}")
    print(f"  {C.DIM}Architecture: {platform.machine()}{C.RESET}")
    print()

    # 1. Python
    results['python'] = check_python_version()

    # 2. venv
    results['venv'] = check_venv_exists()

    # 3. Packages
    if results['venv']:
        header("Package Check")
        missing = check_packages()
        results['packages'] = len(missing) == 0
        results['missing'] = missing
    else:
        results['packages'] = False
        results['missing'] = REQUIRED_PACKAGES[:]

    # 4. Permissions
    header("Permission Check")
    results['permissions'] = check_write_permissions()
    check_admin()

    # 5. PDF backend
    header("PDF Backend Check")
    results['pdf_backend'] = check_docx2pdf_backend()

    # Summary
    header("Summary")
    all_ok = all([
        results['python'],
        results['venv'],
        results['packages'],
        results['permissions'],
    ])

    if all_ok:
        log_ok("All checks passed — ready to run!")
    else:
        if not results['venv']:
            log_fail("Virtual environment missing")
            log_info("  Run: python setup.py  (it will be created automatically)")
        if not results['packages']:
            log_fail("Missing packages: " + ", ".join(results.get('missing', [])))
            log_info("  Run: python setup.py  (they will be installed automatically)")
        if not results['permissions']:
            log_fail("Permission issues detected — see above")
        if not results.get('pdf_backend', True):
            log_warn("PDF backend not found — generation will fail")

    return results


def setup_and_run(launch=True):
    """Full setup: ensure venv, install packages, then launch."""
    header("Bulk Certificate Emailer — Setup")
    print(f"  {C.DIM}Platform: {platform.system()} {platform.release()}{C.RESET}")
    print()

    # 1. Python check
    if not check_python_version():
        log_fail("Python 3.8+ required. Aborting.")
        sys.exit(1)

    # 2. Venv
    if not check_venv_exists():
        if not create_venv():
            sys.exit(1)

    # 3. Install packages
    header("Installing Dependencies")
    missing = check_packages()
    if missing:
        if not install_packages():
            sys.exit(1)
        # Verify
        still_missing = check_packages()
        if still_missing:
            log_fail("Some packages could not be installed: " + ", ".join(still_missing))
            log_info("Try installing manually:")
            log_info(f"  {VENV_PIP} install {' '.join(still_missing)}")
            sys.exit(1)
    else:
        log_ok("All packages already installed")

    # 4. Permissions
    header("Checking Permissions")
    if not check_write_permissions():
        log_warn("Permission issues found — app may not work correctly")

    # 5. PDF backend
    header("PDF Backend")
    check_docx2pdf_backend()

    if not launch:
        print()
        log_ok("Setup complete. Run the app with:")
        log_info(f"  {VENV_PYTHON} app.py")
        return

    # 6. Launch
    header("Launching Application")
    log_info("Starting server at http://127.0.0.1:5050")
    log_info("Press Ctrl+C to stop")
    print()

    os.execv(VENV_PYTHON, [VENV_PYTHON, os.path.join(BASE_DIR, 'app.py')])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Setup Bulk Certificate Emailer')
    parser.add_argument('--check', action='store_true',
                        help='Run health check only (do not launch)')
    parser.add_argument('--no-launch', action='store_true',
                        help='Setup only, do not launch the app')
    args = parser.parse_args()

    if args.check:
        results = health_check()
        sys.exit(0 if all([
            results['python'], results['venv'],
            results['packages'], results['permissions'],
        ]) else 1)
    else:
        setup_and_run(launch=not args.no_launch)
