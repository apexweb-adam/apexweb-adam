"""Tests for /crm landing page."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_crm_landing_includes_monday_recovery_when_candidates():
  client = TestClient(app)
  recovery = {
    "recovery_candidates": ["SI=F", "NVDA"],
    "all": [
      {
        "bot_type": "commodities",
        "symbol": "SI=F",
        "composite": 0.502,
        "blockers": ["weekend_futures_closed", "signal_sell"],
      },
      {
        "bot_type": "stocks_futures",
        "symbol": "NVDA",
        "composite": 0.418,
        "blockers": ["gate_skip"],
      },
    ],
    "bots": {},
  }

  with patch("app.main.recommended_dashboard_url", new_callable=AsyncMock, return_value="https://example.com"):
    with patch("app.main.build_deploy_status", new_callable=AsyncMock, return_value={"vercel_bundle_stale": False}):
      with patch("app.database.SessionLocal") as mock_session_local:
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = None
        mock_session_local.return_value = mock_cm
        with patch("app.engines.profitability_gate.ProfitabilityGate") as MockGate:
          MockGate.return_value.evaluate = AsyncMock(
            return_value={
              "verification_day": 2,
              "total_trades": 31,
              "win_rate": 0.44,
              "total_pnl": 19.13,
              "profit_factor": 1.19,
              "recommendation": "Continue paper trading",
              "paused_bots": ["crypto"],
            }
          )
          MockGate.return_value.evaluate_per_bot = AsyncMock(return_value={})
          with patch(
            "app.engines.scan_preview.build_monday_recovery_summary",
            new_callable=AsyncMock,
            return_value=recovery,
          ):
            response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "Monday recovery watchlist" in body
  assert "SI=F" in body
  assert "NVDA" in body
  assert "weekend_futures_closed" in body
