"""Load Tampermonkey bridge script bundled in the backend image."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_CANDIDATES = (
  _BACKEND_ROOT / "assets" / "fomo-family-bridge.user.js",
  _BACKEND_ROOT / "app" / "static" / "fomo-family-bridge.user.js",
)


@lru_cache(maxsize=1)
def load_fomo_userscript_bytes() -> bytes:
  for path in _SCRIPT_CANDIDATES:
    if path.is_file():
      return path.read_bytes()
  raise FileNotFoundError(
    "fomo-family-bridge.user.js missing; checked: "
    + ", ".join(str(path) for path in _SCRIPT_CANDIDATES)
  )


def fomo_userscript_available() -> bool:
  try:
    load_fomo_userscript_bytes()
    return True
  except FileNotFoundError:
    return False
