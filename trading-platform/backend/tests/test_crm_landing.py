"""Tests for /crm landing page."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_crm_landing_includes_monday_recovery_when_candidates():
  client = TestClient(app)
  recovery = {
    "recovery_candidates": ["SI=F", "NVDA"],
    "stocks_trade_count_nudge": True,
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
    "bots": {
      "stocks_futures": {
        "recovery_candidates": ["NVDA"],
        "stocks_trade_count_nudge": True,
      }
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
          MockGate.return_value.evaluate_per_bot = AsyncMock(
            return_value={
              "stocks_futures": {
                "paused": True,
                "total_trades": 15,
                "win_rate": 0.57,
                "graduation_blockers": ["5 more trades", "profit factor ≥ 1.3", "positive PnL"],
              }
            }
          )
          with patch(
            "app.engines.scan_preview.build_monday_recovery_summary",
            new_callable=AsyncMock,
            return_value=recovery,
          ):
            with patch(
              "app.engines.learning_engine.build_crm_learning_highlights",
              new_callable=AsyncMock,
              return_value={
                "review_date": "2026-08-29",
                "trade_analyses": 0,
                "pending_insights": 0,
                "reviews": [],
              },
            ):
              with patch(
                "app.engines.learning_engine.build_crm_content_study_highlights",
                new_callable=AsyncMock,
                return_value={"insights_applied": 0, "recent": []},
              ):
                with patch(
                  "app.engines.intel_source_status.build_intel_sources",
                  new_callable=AsyncMock,
                  return_value=[{"source": "news", "status": "active"}],
                ):
                  with patch(
                    "app.engines.crm_summary.build_crm_live_snapshot",
                    new_callable=AsyncMock,
                    return_value={
                      "active_bots": ["commodities"],
                      "positions": [],
                      "gate_tightening": {},
                      "chronic_loser_symbols": {},
                      "proven_winner_symbols": {},
                    },
                  ):
                    with patch(
                      "app.engines.crm_summary.build_crm_integration_hooks",
                      new_callable=AsyncMock,
                      return_value={
                        "tradingview": {"configured": True, "webhook_url": "https://example.com/tv", "items": 0},
                        "polymarket": {"api_configured": True, "wallet_configured": True, "profile_url": None, "intel_items": 0, "account_items": 0},
                        "wallet_tracker": {"configured": True, "webhook_url": "https://example.com/wallet"},
                      },
                    ):
                      response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "Monday recovery watchlist" in body
  assert "SI=F" in body
  assert "NVDA" in body
  assert "weekend_futures_closed" in body
  assert "trade-count nudge" in body
  assert "composite floor 0.34" in body


def test_crm_landing_shows_nudge_without_recovery_rows():
  client = TestClient(app)
  recovery = {
    "recovery_candidates": [],
    "stocks_trade_count_nudge": True,
    "commodities_graduation_nudge": False,
    "all": [],
    "bots": {
      "stocks_futures": {
        "recovery_candidates": [],
        "stocks_trade_count_nudge": True,
      }
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
            with patch(
              "app.engines.learning_engine.build_crm_learning_highlights",
              new_callable=AsyncMock,
              return_value={
                "review_date": "2026-08-29",
                "trade_analyses": 0,
                "pending_insights": 0,
                "reviews": [],
              },
            ):
              with patch(
                "app.engines.learning_engine.build_crm_content_study_highlights",
                new_callable=AsyncMock,
                return_value={"insights_applied": 0, "recent": []},
              ):
                with patch(
                  "app.engines.intel_source_status.build_intel_sources",
                  new_callable=AsyncMock,
                  return_value=[{"source": "news", "status": "active"}],
                ):
                  with patch(
                    "app.engines.crm_summary.build_crm_live_snapshot",
                    new_callable=AsyncMock,
                    return_value={
                      "active_bots": ["commodities"],
                      "positions": [],
                      "gate_tightening": {},
                      "chronic_loser_symbols": {},
                      "proven_winner_symbols": {},
                    },
                  ):
                    with patch(
                      "app.engines.crm_summary.build_crm_integration_hooks",
                      new_callable=AsyncMock,
                      return_value={
                        "tradingview": {"configured": True, "webhook_url": "https://example.com/tv", "items": 0},
                        "polymarket": {"api_configured": True, "wallet_configured": True, "profile_url": None, "intel_items": 0, "account_items": 0},
                        "wallet_tracker": {"configured": True, "webhook_url": "https://example.com/wallet"},
                      },
                    ):
                      response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "Monday recovery watchlist" in body
  assert "trade-count nudge" in body
  assert "nudges still active" in body
  assert "SI=F" not in body
