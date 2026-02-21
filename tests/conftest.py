"""Pytest configuration and shared fixtures."""

import sys
from pathlib import Path

# Make sure the repo root is on sys.path so `from app.xxx import ...` works
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SAMPLE_DIR = REPO_ROOT / "sample_cases"
OPENFOAM_CASE = SAMPLE_DIR / "openfoam_dambreak"
FLUENT_CASE = SAMPLE_DIR / "fluent_limestone"
