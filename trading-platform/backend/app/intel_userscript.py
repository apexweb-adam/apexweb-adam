"""Load Tampermonkey bridge scripts bundled in the backend image."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

_SCRIPT_MAP: dict[str, tuple[Path, ...]] = {
  "fomo": (
    _BACKEND_ROOT / "assets" / "fomo-family-bridge.user.js",
    _BACKEND_ROOT / "app" / "static" / "fomo-family-bridge.user.js",
  ),
  "axiom": (
    _BACKEND_ROOT / "assets" / "axiom-trade-bridge.user.js",
    _BACKEND_ROOT / "app" / "static" / "axiom-trade-bridge.user.js",
  ),
  "phantom": (
    _BACKEND_ROOT / "assets" / "phantom-wallet-bridge.user.js",
    _BACKEND_ROOT / "app" / "static" / "phantom-wallet-bridge.user.js",
  ),
}


def _load_script_bytes(name: str) -> bytes:
  for path in _SCRIPT_MAP.get(name, ()):
    if path.is_file():
      return path.read_bytes()
  raise FileNotFoundError(f"{name} bridge userscript missing")


@lru_cache(maxsize=2)
def load_fomo_userscript_bytes() -> bytes:
  return _load_script_bytes("fomo")


@lru_cache(maxsize=2)
def load_axiom_userscript_bytes() -> bytes:
  return _load_script_bytes("axiom")


@lru_cache(maxsize=2)
def load_phantom_userscript_bytes() -> bytes:
  return _load_script_bytes("phantom")


def fomo_userscript_available() -> bool:
  try:
    load_fomo_userscript_bytes()
    return True
  except FileNotFoundError:
    return False


def axiom_userscript_available() -> bool:
  try:
    load_axiom_userscript_bytes()
    return True
  except FileNotFoundError:
    return False


def phantom_userscript_available() -> bool:
  try:
    load_phantom_userscript_bytes()
    return True
  except FileNotFoundError:
    return False
