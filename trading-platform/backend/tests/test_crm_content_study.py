"""Tests for CRM content study highlights."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_build_crm_content_study_highlights_truncates_long_fields():
  from app.engines.learning_engine import build_crm_content_study_highlights

  insight = type(
    "Insight",
    (),
    {
      "source_type": "polymarket",
      "source_title": "A" * 90,
      "strategy_impact": "B" * 150,
      "confidence": 0.73,
      "applied": True,
    },
  )()

  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=type("Result", (), {"scalars": lambda self: type("S", (), {"all": lambda self: [insight]})()})()
  )
  session.scalar = AsyncMock(return_value=42)

  import asyncio

  result = asyncio.run(build_crm_content_study_highlights(session))

  assert result["insights_applied"] == 42
  assert len(result["recent"]) == 1
  assert result["recent"][0]["title"].endswith("…")
  assert result["recent"][0]["impact"].endswith("…")


def test_crm_landing_includes_content_study_section():
  client = TestClient(app)
  content_study = {
    "insights_applied": 88,
    "recent": [
      {
        "source_type": "youtube",
        "title": "Risk Management - Never Risk More Than 2%",
        "impact": "Tighten stop-loss to 1.5-2% max.",
        "confidence": 0.9,
        "applied": True,
      }
    ],
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
            return_value={"recovery_candidates": [], "all": [], "bots": {}},
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
                return_value=content_study,
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
                    response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "External content study" in body
  assert "88 insights applied" in body
  assert "Risk Management" in body
  assert "intel 1/1 sources" in body


def test_crm_landing_includes_live_positions():
  client = TestClient(app)
  live_snapshot = {
    "active_bots": ["commodities"],
    "positions": [
      {
        "bot_type": "commodities",
        "symbol": "CL=F",
        "side": "long",
        "entry_price": 83.44,
        "current_price": 83.4,
        "unrealized_pnl": -0.47,
        "is_active_gate": True,
      }
    ],
    "gate_tightening": {
      "active": True,
      "require_macd_bullish": True,
      "blocked_new_entries": ["crypto"],
    },
    "chronic_loser_symbols": {},
    "proven_winner_symbols": {"commodities": ["SI=F"]},
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
              "paused_bots": ["crypto", "stocks_futures", "polymarket"],
            }
          )
          MockGate.return_value.evaluate_per_bot = AsyncMock(return_value={})
          with patch(
            "app.engines.scan_preview.build_monday_recovery_summary",
            new_callable=AsyncMock,
            return_value={"recovery_candidates": [], "all": [], "bots": {}},
          ):
            with patch(
              "app.engines.learning_engine.build_crm_learning_highlights",
              new_callable=AsyncMock,
              return_value={"review_date": "2026-08-29", "trade_analyses": 0, "pending_insights": 0, "reviews": []},
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
                    return_value=live_snapshot,
                  ):
                    response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "Live gate positions" in body
  assert "CL=F" in body
  assert "Proven winners" in body
  assert "SI=F" in body
