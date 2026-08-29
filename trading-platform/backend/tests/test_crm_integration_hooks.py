"""Tests for CRM integration hooks summary."""

from unittest.mock import AsyncMock, MagicMock, patch

import asyncio

from app.engines.crm_summary import build_crm_integration_hooks


def test_build_crm_integration_hooks_reports_tv_and_polymarket():
  session = AsyncMock()
  session.scalar = AsyncMock(side_effect=[12, 1, 170])

  with patch("app.engines.crm_summary.settings") as mock_settings:
    mock_settings.tradingview_webhook_secret = "secret"
    mock_settings.polymarket_wallet_address = "0xabc"
    mock_settings.polymarket_deposit_address = ""
    mock_settings.polymarket_api_key = "pm-key"
    mock_settings.polymarket_profile_url = "https://polymarket.com/@apexweb"
    mock_settings.fomo_enabled = True
    mock_settings.axiom_enabled = True
    mock_settings.phantom_enabled = True
    mock_settings.wallet_tracker_min_wallets = 8
    with patch(
      "app.engines.crm_summary.wallet_tracker_configured",
      return_value=True,
    ):
      with patch(
        "app.engines.crm_summary.fomo_configured",
        return_value=True,
      ):
        with patch(
          "app.engines.crm_summary.get_fomo_bearer_status",
          AsyncMock(
            return_value={
              "configured": True,
              "polling_active": True,
              "expires_at": "2026-08-29T10:00:00+00:00",
              "minutes_remaining": 45,
            }
          ),
        ):
          with patch(
            "app.engines.crm_summary.axiom_configured",
            return_value=True,
          ):
            with patch(
              "app.engines.crm_summary.phantom_configured",
              return_value=True,
            ):
              with patch(
                "app.engines.crm_summary.get_axiom_session_status",
                AsyncMock(
                  return_value={
                    "configured": False,
                    "polling_active": False,
                    "multi_wallet_ready": True,
                    "tracked_wallets": 8,
                  }
                ),
              ):
                result = asyncio.run(build_crm_integration_hooks(session))

  assert result["tradingview"]["configured"] is True
  assert result["tradingview"]["items"] == 12
  assert result["polymarket"]["wallet_configured"] is True
  assert result["polymarket"]["api_configured"] is True
  assert result["polymarket"]["intel_items"] == 170
  assert result["wallet_tracker"]["configured"] is True
  assert result["fomo"]["configured"] is True
  assert "webhooks/fomo" in result["fomo"]["webhook_url"]
  assert result["axiom"]["configured"] is True
  assert result["axiom"]["multi_wallet_ready"] is True
  assert result["phantom"]["configured"] is True


def test_crm_landing_includes_integration_hooks():
  from unittest.mock import patch

  from fastapi.testclient import TestClient

  from app.main import app

  client = TestClient(app)
  integrations = {
    "tradingview": {
      "configured": True,
      "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/tradingview",
      "items": 12,
    },
    "polymarket": {
      "api_configured": True,
      "wallet_configured": True,
      "profile_url": "https://polymarket.com/@apexweb",
      "intel_items": 170,
      "account_items": 1,
    },
    "wallet_tracker": {
      "configured": True,
      "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/wallet",
    },
    "fomo": {
      "configured": True,
      "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/fomo",
      "userscript_url": "https://apex-trading-backend.onrender.com/api/fomo/userscript",
      "bridge_guide": "trading-platform/scripts/fomo-zapier-setup.md",
    },
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
          MockGate.return_value.evaluate = AsyncMock(return_value={"verification_day": 2, "total_trades": 31, "win_rate": 0.44, "total_pnl": 19.13, "profit_factor": 1.19, "recommendation": "ok", "paused_bots": []})
          MockGate.return_value.evaluate_per_bot = AsyncMock(return_value={})
          with patch("app.engines.scan_preview.build_monday_recovery_summary", new_callable=AsyncMock, return_value={"recovery_candidates": [], "all": [], "bots": {}}):
            with patch("app.engines.learning_engine.build_crm_learning_highlights", new_callable=AsyncMock, return_value={"review_date": "2026-08-29", "trade_analyses": 0, "pending_insights": 0, "reviews": []}):
              with patch("app.engines.learning_engine.build_crm_content_study_highlights", new_callable=AsyncMock, return_value={"insights_applied": 0, "recent": []}):
                with patch("app.engines.intel_source_status.build_intel_sources", new_callable=AsyncMock, return_value=[{"source": "news", "status": "active"}]):
                  with patch("app.engines.crm_summary.build_crm_live_snapshot", new_callable=AsyncMock, return_value={"active_bots": ["commodities"], "positions": [], "gate_tightening": {}, "chronic_loser_symbols": {}, "proven_winner_symbols": {}}):
                    with patch("app.engines.crm_summary.build_crm_integration_hooks", new_callable=AsyncMock, return_value=integrations):
                      response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "TradingView" in body and "fomo" in body
  assert "webhooks/tradingview" in body
  assert "webhooks/fomo" in body
  assert "polymarket.com/@apexweb" in body
