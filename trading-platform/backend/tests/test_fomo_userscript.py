"""Tests for fomo userscript endpoint."""

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_fomo_userscript_served():
  script = Path(__file__).resolve().parents[1] / "assets" / "fomo-family-bridge.user.js"
  assert script.is_file()
  with patch("app.config.settings") as mock_settings:
    mock_settings.fomo_enabled = True
    response = client.get("/api/fomo/userscript")
  assert response.status_code == 200
  assert "apex-fomo-bridge" in response.text
  assert "prod-api.fomo.family" in response.text
  assert "set-fomo-bearer" in response.text
