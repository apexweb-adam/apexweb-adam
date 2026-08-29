"""Tests for CRM learning highlights helper and landing."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_build_crm_learning_highlights_filters_empty_reviews():
  from app.engines.learning_engine import build_crm_learning_highlights

  review_active = type(
    "Review",
    (),
    {
      "bot_type": "crypto",
      "total_trades": 2,
      "losing_trades": 2,
      "win_rate": 0.0,
      "net_pnl": -4.98,
      "patterns_found": "weak signals",
      "strategy_changes": "Raised min signal",
      "conclusions": "Below target",
    },
  )()
  review_quiet = type(
    "Review",
    (),
    {
      "bot_type": "commodities",
      "total_trades": 0,
      "losing_trades": 0,
      "win_rate": 0.0,
      "net_pnl": 0.0,
      "patterns_found": "",
      "strategy_changes": "No changes",
      "conclusions": "No trades",
    },
  )()

  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=type("Result", (), {"scalars": lambda self: type("S", (), {"all": lambda self: [review_active, review_quiet]})()})()
  )
  session.scalar = AsyncMock(side_effect=[12, 3])

  import asyncio

  result = asyncio.run(build_crm_learning_highlights(session))

  assert result["trade_analyses"] == 12
  assert result["pending_insights"] == 3
  assert len(result["reviews"]) == 1
  assert result["reviews"][0]["bot_type"] == "crypto"


def test_crm_landing_includes_learning_section():
  client = TestClient(app)
  learning = {
    "review_date": "2026-08-29",
    "trade_analyses": 8,
    "pending_insights": 2,
    "reviews": [
      {
        "bot_type": "crypto",
        "total_trades": 2,
        "losing_trades": 2,
        "win_rate": 0.0,
        "net_pnl": -4.98,
        "patterns_found": "weak signals",
        "strategy_changes": "Raised minimum signal score threshold by 0.05",
        "conclusions": "Below target",
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
              return_value=learning,
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
                  response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "Today's learning loop" in body
  assert "8 post-mortems" in body
  assert "crypto" in body
  assert "Raised minimum signal score" in body
