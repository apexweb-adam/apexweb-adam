"""Tests for intelligence source health reporting."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.engines.intel_source_status import _source_status


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
