"""Pytest configuration for backend unit tests."""

import sys
from pathlib import Path

# Ensure `app` package resolves when running from repo root or backend dir.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
  sys.path.insert(0, str(BACKEND_ROOT))
