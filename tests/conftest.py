"""
Pytest configuration and shared fixtures for ada_v2 tests.
"""
import pytest
import sys
import os
import json
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Settings file path
SETTINGS_FILE = BACKEND_DIR / "settings.json"


@pytest.fixture(scope="session")
def settings():
    """Load the assistant application settings."""
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {}


@pytest.fixture(scope="session")
def temp_dir(tmp_path):
    """Provide a temporary directory for file operations."""
    return tmp_path
