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


def test_crm_landing_shows_open_ready_card():
  client = TestClient(app)
  recovery = {
    "recovery_candidates": ["NG=F"],
    "commodities_graduation_nudge": True,
    "open_ready": [
      {
        "bot_type": "commodities",
        "symbol": "NG=F",
        "composite": 0.645,
        "direction": "buy",
        "macd": "bullish",
        "blockers": ["weekend_futures_closed"],
        "minutes_until_open": 1260,
        "monday_gate_skip_ready": True,
      },
      {
        "bot_type": "stocks_futures",
        "symbol": "AAPL",
        "composite": 0.467,
        "blockers": ["stocks_session_closed"],
        "minutes_until_open": 2190,
        "monday_gate_skip_ready": True,
      },
    ],
    "all": [],
    "bots": {"commodities": {"recovery_candidates": ["NG=F"], "graduation_nudge": True}},
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
              "verification_day": 3,
              "total_trades": 40,
              "win_rate": 0.5,
              "total_pnl": 20.0,
              "profit_factor": 1.2,
              "recommendation": "Continue paper trading",
              "paused_bots": ["crypto", "stocks_futures"],
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
                    return_value={"active_bots": ["commodities"], "positions": [], "gate_tightening": {}, "chronic_loser_symbols": {}, "proven_winner_symbols": {}},
                  ):
                    with patch(
                      "app.engines.crm_summary.build_crm_integration_hooks",
                      new_callable=AsyncMock,
                      return_value={"tradingview": {"configured": True, "webhook_url": "https://example.com/tv", "items": 0}, "polymarket": {}, "wallet_tracker": {}},
                    ):
                      response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "Session open ready" in body
  assert "NG=F" in body
  assert "AAPL" in body
  assert "gate-skip" in body
  assert "bullish" in body
  assert "prep scan" in body
  assert "21h 0m" in body


def test_crm_landing_shows_cme_imminent_banner():
  client = TestClient(app)
  recovery = {
    "recovery_candidates": ["NG=F"],
    "commodities_graduation_nudge": True,
    "open_ready": [
      {
        "bot_type": "commodities",
        "symbol": "NG=F",
        "composite": 0.645,
        "blockers": ["weekend_futures_closed"],
        "minutes_until_open": 45,
        "monday_gate_skip_ready": True,
      },
    ],
    "all": [],
    "bots": {"commodities": {"recovery_candidates": ["NG=F"], "graduation_nudge": True}},
  }
  imminent_cme = {
    "in_session": False,
    "minutes_until_open": 45,
    "session_open_utc": "2026-08-30T22:00:00",
    "mode": "weekend_closed",
  }
  stocks_session = {
    "in_session": False,
    "minutes_until_open": 2000,
    "session_open_utc": "2026-08-31T13:30:00",
    "mode": "weekend_closed",
  }

  with patch("app.main.recommended_dashboard_url", new_callable=AsyncMock, return_value="https://example.com"):
    with patch("app.main.build_deploy_status", new_callable=AsyncMock, return_value={"vercel_bundle_stale": False}):
      with patch("app.engines.gate_entry_guard.commodities_session_info", return_value=imminent_cme):
        with patch("app.engines.gate_entry_guard.stocks_session_info", return_value=stocks_session):
          with patch("app.database.SessionLocal") as mock_session_local:
            mock_session = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_session
            mock_cm.__aexit__.return_value = None
            mock_session_local.return_value = mock_cm
            with patch("app.engines.profitability_gate.ProfitabilityGate") as MockGate:
              MockGate.return_value.evaluate = AsyncMock(
                return_value={
                  "verification_day": 3,
                  "total_trades": 40,
                  "win_rate": 0.5,
                  "total_pnl": 20.0,
                  "profit_factor": 1.2,
                  "recommendation": "Continue paper trading",
                  "paused_bots": ["crypto", "stocks_futures"],
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
                        return_value={"active_bots": ["commodities"], "positions": [], "gate_tightening": {}, "chronic_loser_symbols": {}, "proven_winner_symbols": {}},
                      ):
                        with patch(
                          "app.engines.crm_summary.build_crm_integration_hooks",
                          new_callable=AsyncMock,
                          return_value={"tradingview": {"configured": True, "webhook_url": "https://example.com/tv", "items": 0}, "polymarket": {}, "wallet_tracker": {}},
                        ):
                          response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "CME reopen imminent" in body
  assert "45m until open" in body
  assert "NG=F" in body
  assert "Gate-skip auto-entry queued" in body


def test_crm_landing_shows_next_sessions_card():
  client = TestClient(app)
  recovery = {
    "recovery_candidates": ["NG=F"],
    "commodities_graduation_nudge": True,
    "open_ready": [
      {
        "bot_type": "commodities",
        "symbol": "NG=F",
        "composite": 0.645,
        "blockers": ["weekend_futures_closed"],
        "minutes_until_open": 1260,
        "monday_gate_skip_ready": True,
      },
      {
        "bot_type": "commodities",
        "symbol": "CL=F",
        "composite": 0.44,
        "blockers": ["weekend_futures_closed"],
        "minutes_until_open": 1260,
        "monday_gate_skip_ready": True,
      },
      {
        "bot_type": "stocks_futures",
        "symbol": "AAPL",
        "composite": 0.467,
        "blockers": ["stocks_session_closed"],
        "minutes_until_open": 2190,
        "monday_gate_skip_ready": True,
      },
    ],
    "all": [],
    "bots": {"commodities": {"recovery_candidates": ["NG=F"], "graduation_nudge": True}},
  }
  cme_session = {
    "in_session": False,
    "minutes_until_open": 1260,
    "session_open_utc": "2026-08-30T22:00:00",
    "mode": "weekend_closed",
  }
  stocks_session = {
    "in_session": False,
    "minutes_until_open": 2190,
    "session_open_utc": "2026-08-31T13:30:00",
    "mode": "weekend_closed",
  }

  with patch("app.main.recommended_dashboard_url", new_callable=AsyncMock, return_value="https://example.com"):
    with patch("app.main.build_deploy_status", new_callable=AsyncMock, return_value={"vercel_bundle_stale": False}):
      with patch("app.engines.gate_entry_guard.commodities_session_info", return_value=cme_session):
        with patch("app.engines.gate_entry_guard.stocks_session_info", return_value=stocks_session):
          with patch("app.database.SessionLocal") as mock_session_local:
            mock_session = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_session
            mock_cm.__aexit__.return_value = None
            mock_session_local.return_value = mock_cm
            with patch("app.engines.profitability_gate.ProfitabilityGate") as MockGate:
              MockGate.return_value.evaluate = AsyncMock(
                return_value={
                  "verification_day": 3,
                  "total_trades": 40,
                  "win_rate": 0.5,
                  "total_pnl": 20.0,
                  "profit_factor": 1.2,
                  "recommendation": "Continue paper trading",
                  "paused_bots": ["crypto", "stocks_futures"],
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
                        return_value={"active_bots": ["commodities"], "positions": [], "gate_tightening": {}, "chronic_loser_symbols": {}, "proven_winner_symbols": {}},
                      ):
                        with patch(
                          "app.engines.crm_summary.build_crm_integration_hooks",
                          new_callable=AsyncMock,
                          return_value={"tradingview": {"configured": True, "webhook_url": "https://example.com/tv", "items": 0}, "polymarket": {}, "wallet_tracker": {}},
                        ):
                          response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "Next sessions" in body
  assert "Gate-skip eligible" in body
  assert "prep scan" in body
  assert "CME reopen" in body
  assert "US stocks open" in body
  assert "NG=F, CL=F" in body
  assert "AAPL" in body
  assert "composite floor" in body.lower()
  assert "fast scan in" in body


def test_crm_landing_auto_refreshes():
  client = TestClient(app)
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
              "verification_day": 1,
              "total_trades": 10,
              "win_rate": 0.5,
              "total_pnl": 0.0,
              "profit_factor": 1.0,
              "recommendation": "Continue",
              "paused_bots": [],
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
              return_value={"review_date": "", "trade_analyses": 0, "pending_insights": 0, "reviews": []},
            ):
              with patch(
                "app.engines.learning_engine.build_crm_content_study_highlights",
                new_callable=AsyncMock,
                return_value={"insights_applied": 0, "recent": []},
              ):
                with patch(
                  "app.engines.intel_source_status.build_intel_sources",
                  new_callable=AsyncMock,
                  return_value=[],
                ):
                  with patch(
                    "app.engines.crm_summary.build_crm_live_snapshot",
                    new_callable=AsyncMock,
                    return_value={"active_bots": [], "positions": [], "gate_tightening": {}, "chronic_loser_symbols": {}, "proven_winner_symbols": {}},
                  ):
                    with patch(
                      "app.engines.crm_summary.build_crm_integration_hooks",
                      new_callable=AsyncMock,
                      return_value={"tradingview": {}, "polymarket": {}, "wallet_tracker": {}},
                    ):
                      response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert 'http-equiv="refresh"' in body
  assert 'content="60"' in body


def test_crm_landing_shows_fomo_bearer_alert():
  client = TestClient(app)
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
              "verification_day": 1,
              "total_trades": 10,
              "win_rate": 0.5,
              "total_pnl": 0.0,
              "profit_factor": 1.0,
              "recommendation": "Continue",
              "paused_bots": [],
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
              return_value={"review_date": "", "trade_analyses": 0, "pending_insights": 0, "reviews": []},
            ):
              with patch(
                "app.engines.learning_engine.build_crm_content_study_highlights",
                new_callable=AsyncMock,
                return_value={"insights_applied": 0, "recent": []},
              ):
                with patch(
                  "app.engines.intel_source_status.build_intel_sources",
                  new_callable=AsyncMock,
                  return_value=[{"source": "fomo", "status": "degraded"}],
                ):
                  with patch(
                    "app.engines.crm_summary.build_crm_live_snapshot",
                    new_callable=AsyncMock,
                    return_value={"active_bots": [], "positions": [], "gate_tightening": {}, "chronic_loser_symbols": {}, "proven_winner_symbols": {}},
                  ):
                    with patch(
                      "app.engines.crm_summary.build_crm_integration_hooks",
                      new_callable=AsyncMock,
                      return_value={
                        "fomo": {
                          "configured": True,
                          "bearer_configured": True,
                          "bearer_polling_active": False,
                        },
                        "tradingview": {},
                        "polymarket": {},
                        "wallet_tracker": {},
                      },
                    ):
                      response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "fomo.family bearer expired" in body
  assert "fomo-set-bearer.sh" in body


def test_crm_landing_shows_us_stocks_imminent_banner():
  client = TestClient(app)
  recovery = {
    "recovery_candidates": ["AAPL"],
    "stocks_trade_count_nudge": True,
    "open_ready": [
      {
        "bot_type": "stocks_futures",
        "symbol": "AAPL",
        "composite": 0.467,
        "blockers": ["stocks_session_closed"],
        "minutes_until_open": 30,
        "monday_gate_skip_ready": True,
      },
    ],
    "all": [],
    "bots": {"stocks_futures": {"recovery_candidates": ["AAPL"], "stocks_trade_count_nudge": True}},
  }
  cme_session = {
    "in_session": True,
    "minutes_until_open": 0,
    "minutes_since_open": 120,
    "mode": "in_session",
  }
  stocks_session = {
    "in_session": False,
    "minutes_until_open": 30,
    "session_open_utc": "2026-08-31T13:30:00",
    "mode": "outside_session",
  }

  with patch("app.main.recommended_dashboard_url", new_callable=AsyncMock, return_value="https://example.com"):
    with patch("app.main.build_deploy_status", new_callable=AsyncMock, return_value={"vercel_bundle_stale": False}):
      with patch("app.engines.gate_entry_guard.commodities_session_info", return_value=cme_session):
        with patch("app.engines.gate_entry_guard.stocks_session_info", return_value=stocks_session):
          with patch("app.database.SessionLocal") as mock_session_local:
            mock_session = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_session
            mock_cm.__aexit__.return_value = None
            mock_session_local.return_value = mock_cm
            with patch("app.engines.profitability_gate.ProfitabilityGate") as MockGate:
              MockGate.return_value.evaluate = AsyncMock(
                return_value={
                  "verification_day": 3,
                  "total_trades": 40,
                  "win_rate": 0.5,
                  "total_pnl": 20.0,
                  "profit_factor": 1.2,
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
                        return_value={"active_bots": ["commodities"], "positions": [], "gate_tightening": {}, "chronic_loser_symbols": {}, "proven_winner_symbols": {}},
                      ):
                        with patch(
                          "app.engines.crm_summary.build_crm_integration_hooks",
                          new_callable=AsyncMock,
                          return_value={"tradingview": {"configured": True, "webhook_url": "https://example.com/tv", "items": 0}, "polymarket": {}, "wallet_tracker": {}},
                        ):
                          response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "US stocks open imminent" in body
  assert "30m until open" in body
  assert "AAPL" in body


def test_crm_landing_shows_cme_deploy_nudge_when_revision_behind():
  client = TestClient(app)
  recovery = {"recovery_candidates": [], "open_ready": [], "all": [], "bots": {}}
  imminent_cme = {
    "in_session": False,
    "minutes_until_open": 180,
    "session_open_utc": "2026-08-30T22:00:00",
    "mode": "weekend_closed",
  }
  stocks_session = {
    "in_session": False,
    "minutes_until_open": 2000,
    "session_open_utc": "2026-08-31T13:30:00",
    "mode": "weekend_closed",
  }
  deploy_status = {
    "vercel_bundle_stale": False,
    "is_stale": False,
    "platform_revision": "2026-08-29-r336",
    "expected_platform_revision": "2026-08-29-r339",
    "platform_revision_current": False,
  }

  with patch("app.main.recommended_dashboard_url", new_callable=AsyncMock, return_value="https://example.com"):
    with patch("app.main.build_deploy_status", new_callable=AsyncMock, return_value=deploy_status):
      with patch("app.engines.gate_entry_guard.commodities_session_info", return_value=imminent_cme):
        with patch("app.engines.gate_entry_guard.stocks_session_info", return_value=stocks_session):
          with patch("app.database.SessionLocal") as mock_session_local:
            mock_session = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_session
            mock_cm.__aexit__.return_value = None
            mock_session_local.return_value = mock_cm
            with patch("app.engines.profitability_gate.ProfitabilityGate") as MockGate:
              MockGate.return_value.evaluate = AsyncMock(
                return_value={
                  "verification_day": 3,
                  "total_trades": 40,
                  "win_rate": 0.5,
                  "total_pnl": 20.0,
                  "profit_factor": 1.2,
                  "recommendation": "Continue paper trading",
                  "paused_bots": ["crypto", "stocks_futures"],
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
                        return_value={"active_bots": ["commodities"], "positions": [], "gate_tightening": {}, "chronic_loser_symbols": {}, "proven_winner_symbols": {}},
                      ):
                        with patch(
                          "app.engines.crm_summary.build_crm_integration_hooks",
                          new_callable=AsyncMock,
                          return_value={"tradingview": {"configured": True}, "polymarket": {}, "wallet_tracker": {}},
                        ):
                          response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "revision behind" in body
  assert "sync-render-env.sh" in body
  assert "CME reopen in 3h 0m" in body


def test_crm_landing_shows_deploy_window_countdown_when_revision_behind():
  client = TestClient(app)
  recovery = {"recovery_candidates": [], "open_ready": [], "all": [], "bots": {}}
  far_cme = {
    "in_session": False,
    "minutes_until_open": 500,
    "session_open_utc": "2026-08-30T22:00:00",
    "mode": "weekend_closed",
  }
  stocks_session = {
    "in_session": False,
    "minutes_until_open": 2000,
    "session_open_utc": "2026-08-31T13:30:00",
    "mode": "weekend_closed",
  }
  deploy_status = {
    "vercel_bundle_stale": False,
    "is_stale": False,
    "platform_revision": "2026-08-29-r336",
    "expected_platform_revision": "2026-08-29-r355",
    "platform_revision_current": False,
  }

  with patch("app.main.recommended_dashboard_url", new_callable=AsyncMock, return_value="https://example.com"):
    with patch("app.main.build_deploy_status", new_callable=AsyncMock, return_value=deploy_status):
      with patch("app.engines.gate_entry_guard.commodities_session_info", return_value=far_cme):
        with patch("app.engines.gate_entry_guard.stocks_session_info", return_value=stocks_session):
          with patch("app.database.SessionLocal") as mock_session_local:
            mock_session = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_session
            mock_cm.__aexit__.return_value = None
            mock_session_local.return_value = mock_cm
            with patch("app.engines.profitability_gate.ProfitabilityGate") as MockGate:
              MockGate.return_value.evaluate = AsyncMock(
                return_value={
                  "verification_day": 3,
                  "total_trades": 40,
                  "win_rate": 0.5,
                  "total_pnl": 20.0,
                  "profit_factor": 1.2,
                  "recommendation": "Continue paper trading",
                  "paused_bots": ["crypto", "stocks_futures"],
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
                        return_value={"active_bots": ["commodities"], "positions": [], "gate_tightening": {}, "chronic_loser_symbols": {}, "proven_winner_symbols": {}},
                      ):
                        with patch(
                          "app.engines.crm_summary.build_crm_integration_hooks",
                          new_callable=AsyncMock,
                          return_value={"tradingview": {"configured": True}, "polymarket": {}, "wallet_tracker": {}},
                        ):
                          response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "CME deploy window countdown" in body
  assert "Deploy window opens in" in body
  assert "verify-pre-deploy.sh" in body


def test_crm_landing_shows_cme_deploy_nudge_when_revision_behind():
  client = TestClient(app)
  recovery = {"recovery_candidates": [], "open_ready": [], "all": [], "bots": {}}
  checklist = {
    "phase": "preflight",
    "ready": True,
    "minutes_until_open": 900,
    "open_ready": {"symbols": ["NG=F", "CL=F"], "composite_floor": 0.42},
    "checks": [
      {"id": "auto_entry_queued", "status": "pass", "message": "Gate-skip auto-entry queued: NG=F, CL=F"},
    ],
  }
  cme_session = {
    "in_session": False,
    "minutes_until_open": 900,
    "session_open_utc": "2026-08-30T22:00:00",
    "mode": "weekend_closed",
  }
  stocks_session = {
    "in_session": False,
    "minutes_until_open": 2000,
    "session_open_utc": "2026-08-31T13:30:00",
    "mode": "weekend_closed",
  }

  with patch("app.main.recommended_dashboard_url", new_callable=AsyncMock, return_value="https://example.com"):
    with patch("app.main.build_deploy_status", new_callable=AsyncMock, return_value={"vercel_bundle_stale": False}):
      with patch("app.engines.gate_entry_guard.commodities_session_info", return_value=cme_session):
        with patch("app.engines.gate_entry_guard.stocks_session_info", return_value=stocks_session):
          with patch("app.database.SessionLocal") as mock_session_local:
            mock_session = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_session
            mock_cm.__aexit__.return_value = None
            mock_session_local.return_value = mock_cm
            with patch("app.engines.profitability_gate.ProfitabilityGate") as MockGate:
              MockGate.return_value.evaluate = AsyncMock(
                return_value={
                  "verification_day": 3,
                  "total_trades": 40,
                  "win_rate": 0.5,
                  "total_pnl": 20.0,
                  "profit_factor": 1.2,
                  "recommendation": "Continue paper trading",
                  "paused_bots": [],
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
                        return_value={"active_bots": ["commodities"], "positions": [], "gate_tightening": {}, "chronic_loser_symbols": {}, "proven_winner_symbols": {}},
                      ):
                        with patch(
                          "app.engines.crm_summary.build_crm_integration_hooks",
                          new_callable=AsyncMock,
                          return_value={"tradingview": {"configured": True}, "polymarket": {}, "wallet_tracker": {}},
                        ):
                          with patch(
                            "app.engines.cme_reopen_checklist.build_cme_reopen_checklist",
                            new_callable=AsyncMock,
                            return_value=checklist,
                          ):
                            with patch(
                              "app.engines.session_open_log.get_session_open_events",
                              new_callable=AsyncMock,
                              return_value=[],
                            ):
                              response = client.get("/crm")

  assert response.status_code == 200
  body = response.text
  assert "CME reopen checklist" in body
  assert "auto_entry_queued" in body
  assert "NG=F" in body
