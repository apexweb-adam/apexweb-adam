"""Tests for intelligence source health reporting."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.engines.intel_source_status import _source_status


def test_reddit_degraded_without_oauth_status():
  status = _source_status(
    "reddit",
    source_counts={"reddit": 5},
    source_latest={"reddit": datetime.now(timezone.utc)},
    configured={"reddit": True, "reddit_oauth": False},
  )
  assert status == "degraded"


def test_tiktok_active_when_recent_items():
  latest = datetime.now(timezone.utc) - timedelta(hours=2)
  status = _source_status(
    "tiktok",
    source_counts={"tiktok": 10},
    source_latest={"tiktok": latest},
    configured={"tiktok": True},
  )
  assert status == "active"


def test_tiktok_degraded_when_stale():
  latest = datetime.now(timezone.utc) - timedelta(hours=20)
  status = _source_status(
    "tiktok",
    source_counts={"tiktok": 10},
    source_latest={"tiktok": latest},
    configured={"tiktok": True},
  )
  assert status == "degraded"


def test_tiktok_active_with_timezone_aware_latest():
  latest = datetime.now(timezone.utc) - timedelta(hours=1)
  status = _source_status(
    "tiktok",
    source_counts={"tiktok": 5},
    source_latest={"tiktok": latest},
    configured={"tiktok": True},
  )
  assert status == "active"


def test_build_intel_sources_includes_tiktok():
  import asyncio
  from app.engines.intel_source_status import build_intel_sources

  session = AsyncMock()
  now = datetime.now(timezone.utc)
  session.execute = AsyncMock(
    return_value=type(
      "Result",
      (),
      {
        "all": lambda self: [
          ("tiktok", now - timedelta(hours=1)),
          ("news", now),
        ]
      },
    )()
  )

  with patch("app.engines.intel_source_status.settings") as mock_settings:
    mock_settings.reddit_client_id = ""
    mock_settings.reddit_client_secret = ""
    mock_settings.polymarket_wallet_address = "0xabc"
    mock_settings.polymarket_deposit_address = ""
    mock_settings.tradingview_webhook_secret = "secret"
    mock_settings.twitter_bearer_token = "token"
    mock_settings.newsapi_key = "key"
    mock_settings.hyperliquid_enabled = True
    with patch(
      "app.engines.intel_source_status.wallet_tracker_configured",
      return_value=True,
    ):
      with patch(
        "app.engines.intel_source_status.get_fomo_bearer_status",
        AsyncMock(return_value={"configured": False, "polling_active": False}),
      ):
        with patch(
          "app.engines.intel_source_status.get_axiom_session_status",
          AsyncMock(
            return_value={
              "configured": False,
              "polling_active": False,
              "multi_wallet_ready": True,
              "tracked_wallets": 8,
            }
          ),
        ):
          sources = asyncio.run(build_intel_sources(session))

  tiktok = next(s for s in sources if s["source"] == "tiktok")
  assert tiktok["status"] == "active"


def test_reddit_degraded_without_oauth():
  import asyncio
  from app.engines.intel_source_status import build_intel_sources

  session = AsyncMock()
  now = datetime.now(timezone.utc)
  session.execute = AsyncMock(
    return_value=type(
      "Result",
      (),
      {
        "all": lambda self: [
          ("reddit", now - timedelta(hours=1)),
        ]
      },
    )()
  )

  with patch("app.engines.intel_source_status.settings") as mock_settings:
    mock_settings.reddit_client_id = ""
    mock_settings.reddit_client_secret = ""
    mock_settings.polymarket_wallet_address = "0xabc"
    mock_settings.polymarket_deposit_address = ""
    mock_settings.tradingview_webhook_secret = "secret"
    mock_settings.twitter_bearer_token = "token"
    mock_settings.newsapi_key = "key"
    mock_settings.hyperliquid_enabled = True
    with patch(
      "app.engines.intel_source_status.wallet_tracker_configured",
      return_value=True,
    ):
      with patch(
        "app.engines.intel_source_status.get_fomo_bearer_status",
        AsyncMock(return_value={"configured": False, "polling_active": False}),
      ):
        with patch(
          "app.engines.intel_source_status.get_axiom_session_status",
          AsyncMock(
            return_value={
              "configured": False,
              "polling_active": False,
              "multi_wallet_ready": True,
              "tracked_wallets": 8,
            }
          ),
        ):
          sources = asyncio.run(build_intel_sources(session))

  reddit = next(s for s in sources if s["source"] == "reddit")
  assert reddit["status"] == "degraded"
  assert reddit["oauth_configured"] is False


def test_fomo_active_when_bearer_expired_but_recent_webhook_items():
  import asyncio
  from app.engines.intel_source_status import build_intel_sources

  session = AsyncMock()
  now = datetime.now(timezone.utc)
  session.execute = AsyncMock(
    return_value=type(
      "Result",
      (),
      {
        "all": lambda self: [
          ("fomo", now - timedelta(hours=2)),
        ]
      },
    )()
  )

  with patch("app.engines.intel_source_status.settings") as mock_settings:
    mock_settings.reddit_client_id = ""
    mock_settings.reddit_client_secret = ""
    mock_settings.polymarket_wallet_address = ""
    mock_settings.polymarket_deposit_address = ""
    mock_settings.tradingview_webhook_secret = "secret"
    mock_settings.twitter_bearer_token = ""
    mock_settings.newsapi_key = ""
    mock_settings.hyperliquid_enabled = False
    mock_settings.phantom_portfolio_poll_enabled = False
    with patch(
      "app.engines.intel_source_status.wallet_tracker_configured",
      return_value=False,
    ):
      with patch(
        "app.engines.intel_source_status.fomo_configured",
        return_value=True,
      ):
        with patch(
          "app.engines.intel_source_status.get_fomo_bearer_status",
          AsyncMock(
            return_value={
              "configured": True,
              "polling_active": False,
              "expired": True,
            }
          ),
        ):
          with patch(
            "app.engines.intel_source_status.get_axiom_session_status",
            AsyncMock(
              return_value={
                "configured": False,
                "polling_active": False,
                "poll_mode": "off",
                "multi_wallet_ready": False,
                "tracked_wallets": 0,
              }
            ),
          ):
            sources = asyncio.run(build_intel_sources(session))

  fomo = next(s for s in sources if s["source"] == "fomo")
  assert fomo["status"] == "active"
  assert fomo["webhook_fallback_active"] is True
  assert fomo["webhook_recent"] is True
