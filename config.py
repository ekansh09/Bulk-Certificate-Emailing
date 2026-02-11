"""
Application configuration and path management.

Author: Ekansh Chauhan
"""

import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
CERT_DIR = os.path.join(BASE_DIR, 'certificates')
LOG_FILE = os.path.join(BASE_DIR, 'app.log')
FAILED_FILE = os.path.join(BASE_DIR, 'failed_list.csv')

for _d in (UPLOAD_DIR, CERT_DIR):
    os.makedirs(_d, exist_ok=True)


def load_config():
    """Load saved configuration from disk."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_config(cfg):
    """Persist configuration to disk."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)
