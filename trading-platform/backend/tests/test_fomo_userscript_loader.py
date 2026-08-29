"""Tests for fomo userscript loader."""

from app.fomo_userscript import fomo_userscript_available, load_fomo_userscript_bytes


def test_fomo_userscript_loader():
  assert fomo_userscript_available()
  body = load_fomo_userscript_bytes()
  assert b"apex-fomo-bridge" in body
  assert b"prod-api.fomo.family" in body
