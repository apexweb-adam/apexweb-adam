"""Tests for intelligence source health reporting."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.engines.intel_source_status import (
  _source_status,
  _x_source_status,
  x_intel_collection_mode,
)


@pytest.fixture(autouse=True)
def _stub_intel_scan_heartbeats():
  with patch(
    "app.intelligence.scan_heartbeats.get_intel_scan_heartbeats",
    AsyncMock(return_value={}),
  ):
    yield


@pytest.fixture(autouse=True)
def _stub_tradingview_breakdown(request):
  """Default stub unless test name exercises TV breakdown."""
  if request.node.name in (
    "test_tradingview_item_breakdown_counts_synthetic_and_webhook",
    "test_tradingview_breakdown_in_intel_sources",
  ):
    yield
    return
  with patch(
    "app.engines.intel_source_status.tradingview_item_breakdown",
    AsyncMock(return_value={"synthetic_items_24h": 0, "webhook_items_24h": 0}),
  ):
    yield


def test_x_intel_collection_mode_google_news_when_no_keys():
  with patch("app.engines.intel_source_status.settings") as mock_settings:
    mock_settings.twitter_bearer_token = ""
    mock_settings.newsapi_key = ""
    assert x_intel_collection_mode() == "google_news_rss"


def test_x_intel_collection_mode_twitter_api():
  with patch("app.engines.intel_source_status.settings") as mock_settings:
    mock_settings.twitter_bearer_token = "token"
    mock_settings.newsapi_key = "key"
    assert x_intel_collection_mode() == "twitter_api"


def test_x_google_news_pending_without_items():
  with patch("app.engines.intel_source_status.x_intel_collection_mode", return_value="google_news_rss"):
    status = _x_source_status(source_counts={}, source_latest={})
  assert status == "pending"


def test_x_google_news_active_with_recent_items():
  latest = datetime.now(timezone.utc) - timedelta(hours=1)
  with patch("app.engines.intel_source_status.x_intel_collection_mode", return_value="google_news_rss"):
    status = _x_source_status(
      source_counts={"x": 3},
      source_latest={"x": latest},
    )
  assert status == "active"


def test_x_google_news_degraded_when_stale():
  latest = datetime.now(timezone.utc) - timedelta(hours=20)
  with patch("app.engines.intel_source_status.x_intel_collection_mode", return_value="google_news_rss"):
    status = _x_source_status(
      source_counts={"x": 3},
      source_latest={"x": latest},
    )
  assert status == "degraded"


def test_x_twitter_active_with_recent_scan_heartbeat():
  heartbeat = datetime.utcnow() - timedelta(minutes=10)
  with patch("app.engines.intel_source_status.x_intel_collection_mode", return_value="twitter_api"):
    status = _x_source_status(
      source_counts={"x": 100},
      source_latest={"x": datetime.utcnow() - timedelta(days=2)},
      scan_heartbeats={"x": heartbeat},
    )
  assert status == "active"


def test_youtube_active_with_recent_scan_heartbeat():
  heartbeat = datetime.utcnow() - timedelta(hours=2)
  status = _source_status(
    "youtube",
    source_counts={"youtube": 5},
    source_latest={"youtube": datetime.utcnow() - timedelta(days=2)},
    configured={"youtube": True},
    scan_heartbeats={"youtube": heartbeat},
  )
  assert status == "active"


def test_reddit_active_via_rss_without_oauth_status():
  status = _source_status(
    "reddit",
    source_counts={"reddit": 5},
    source_latest={"reddit": datetime.now(timezone.utc)},
    configured={"reddit": True, "reddit_oauth": False},
  )
  assert status == "active"


def test_reddit_degraded_without_oauth_when_stale():
  status = _source_status(
    "reddit",
    source_counts={"reddit": 5},
    source_latest={"reddit": datetime.now(timezone.utc) - timedelta(hours=30)},
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
          ("tiktok", 10, now - timedelta(hours=1)),
          ("news", 5, now),
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
          ("reddit", 5, now - timedelta(hours=1)),
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
  assert reddit["status"] == "active"
  assert reddit["oauth_configured"] is False
  assert reddit["collection_mode"] == "rss"


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
          ("fomo", 3, now - timedelta(hours=2)),
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


def test_x_google_news_rss_collection_mode_without_api_keys():
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
          ("x", 4, now - timedelta(hours=2)),
        ]
      },
    )()
  )

  with patch("app.engines.intel_source_status.settings") as mock_settings:
    mock_settings.reddit_client_id = ""
    mock_settings.reddit_client_secret = ""
    mock_settings.polymarket_wallet_address = ""
    mock_settings.polymarket_deposit_address = ""
    mock_settings.tradingview_webhook_secret = ""
    mock_settings.twitter_bearer_token = ""
    mock_settings.newsapi_key = ""
    mock_settings.hyperliquid_enabled = False
    mock_settings.phantom_portfolio_poll_enabled = False
    with patch(
      "app.engines.intel_source_status.wallet_tracker_configured",
      return_value=False,
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
              "poll_mode": "off",
              "multi_wallet_ready": False,
              "tracked_wallets": 0,
            }
          ),
        ):
          sources = asyncio.run(build_intel_sources(session))

  x_row = next(s for s in sources if s["source"] == "x")
  assert x_row["collection_mode"] == "google_news_rss"
  assert x_row["status"] == "active"


def test_tradingview_item_breakdown_counts_synthetic_and_webhook():
  import asyncio
  from app.engines.integration_signals import SYNTHETIC_INTEL_CATEGORY
  from app.engines.intel_source_status import tradingview_item_breakdown

  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=type(
      "Result",
      (),
      {
        "all": lambda self: [
          (SYNTHETIC_INTEL_CATEGORY, 2),
          ("technical", 1),
        ]
      },
    )()
  )

  breakdown = asyncio.run(tradingview_item_breakdown(session))
  assert breakdown == {"synthetic_items_24h": 2, "webhook_items_24h": 1}


def test_tradingview_breakdown_in_intel_sources():
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
          ("tradingview", 3, now),
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
      return_value=True,
    ):
      with patch(
        "app.engines.intel_source_status.tradingview_item_breakdown",
        AsyncMock(return_value={"synthetic_items_24h": 2, "webhook_items_24h": 1}),
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
                "poll_mode": "off",
                "multi_wallet_ready": False,
                "tracked_wallets": 0,
              }
            ),
          ):
            sources = asyncio.run(build_intel_sources(session))

  tv = next(s for s in sources if s["source"] == "tradingview")
  assert tv["synthetic_items_24h"] == 2
  assert tv["webhook_items_24h"] == 1
  assert tv["scoring_excludes_synthetic"] is True
