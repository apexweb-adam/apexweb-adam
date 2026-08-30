"""Tests for degraded intel source weighting and hot-symbol gating."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.intel_source_status import (
  DEGRADED_INTEL_WEIGHT,
  PARTIAL_INTEL_WEIGHT,
  clear_intel_weight_multipliers_cache,
  get_intel_weight_multipliers,
  intel_source_feed_active,
  intel_source_trusted_for_confluence,
)
from app.engines.integration_signals import get_integration_boost
from app.models.entities import IntelligenceItem


def test_intel_source_trusted_for_confluence():
  assert intel_source_trusted_for_confluence("fomo", {"fomo": PARTIAL_INTEL_WEIGHT})
  assert not intel_source_trusted_for_confluence("fomo", {"fomo": DEGRADED_INTEL_WEIGHT})
  assert intel_source_trusted_for_confluence("fomo", {})


def test_degraded_fomo_weight_multiplier():
  clear_intel_weight_multipliers_cache()
  session = AsyncMock()

  with (
    patch(
      "app.engines.intel_source_status.get_fomo_bearer_status",
      AsyncMock(return_value={"configured": True, "polling_active": False}),
    ),
    patch(
      "app.engines.intel_source_status.get_axiom_session_status",
      AsyncMock(
        return_value={
          "configured": True,
          "polling_active": True,
          "poll_mode": "mirror",
          "multi_wallet_ready": True,
        }
      ),
    ),
    patch(
      "app.engines.intel_source_status._source_has_recent_items",
      AsyncMock(return_value=False),
    ),
    patch("app.engines.intel_source_status.phantom_portfolio_poll_active", return_value=True),
  ):
    multipliers = asyncio.run(get_intel_weight_multipliers(session))

  assert multipliers["fomo"] == DEGRADED_INTEL_WEIGHT


def test_partial_fomo_weight_when_webhook_recent():
  clear_intel_weight_multipliers_cache()
  session = AsyncMock()

  async def recent_items(sess, source, *, hours=6):
    return source == "fomo"

  with (
    patch(
      "app.engines.intel_source_status.get_fomo_bearer_status",
      AsyncMock(return_value={"configured": True, "polling_active": False}),
    ),
    patch(
      "app.engines.intel_source_status.get_axiom_session_status",
      AsyncMock(
        return_value={
          "configured": True,
          "polling_active": True,
          "poll_mode": "mirror",
          "multi_wallet_ready": True,
        }
      ),
    ),
    patch(
      "app.engines.intel_source_status._source_has_recent_items",
      side_effect=recent_items,
    ),
    patch("app.engines.intel_source_status.phantom_portfolio_poll_active", return_value=True),
  ):
    multipliers = asyncio.run(get_intel_weight_multipliers(session))

  assert multipliers["fomo"] == PARTIAL_INTEL_WEIGHT


def test_fomo_hot_symbols_blocked_when_feed_inactive():
  from app.intelligence.fomo_tracker import get_fomo_hot_symbols

  session = AsyncMock()
  with (
    patch("app.intelligence.fomo_tracker.settings") as mock_settings,
    patch(
      "app.engines.intel_source_status.intel_source_feed_active",
      AsyncMock(return_value=False),
    ),
  ):
    mock_settings.fomo_hot_symbols_enabled = True
    hot = asyncio.run(get_fomo_hot_symbols(session))

  assert hot == []
  session.execute.assert_not_called()


def test_fomo_leader_confluence_skipped_when_degraded():
  session = AsyncMock()
  items = [
    IntelligenceItem(
      source="fomo",
      category="crypto",
      title="fomo buy",
      content="WIFUSDT",
      url="fomo:1",
      sentiment=0.6,
      relevance_score=0.92,
      symbols_mentioned="WIFUSDT",
      fetched_at=datetime.utcnow(),
    ),
    IntelligenceItem(
      source="dexscreener",
      category="crypto",
      title="dex pump",
      content="WIFUSDT",
      url="dex:1",
      sentiment=0.45,
      relevance_score=0.8,
      symbols_mentioned="WIFUSDT",
      fetched_at=datetime.utcnow(),
    ),
  ]
  session.execute = AsyncMock(
    return_value=MagicMock(
      scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
    )
  )

  with patch(
    "app.engines.integration_signals.get_intel_weight_multipliers",
    AsyncMock(return_value={"fomo": DEGRADED_INTEL_WEIGHT}),
  ):
    boost, reason = asyncio.run(get_integration_boost(session, "WIFUSDT"))

  assert "fomo_leader_confluence" not in reason


def test_intel_source_feed_active_fomo_polling():
  session = AsyncMock()
  with patch(
    "app.engines.intel_source_status.get_fomo_bearer_status",
    AsyncMock(return_value={"configured": True, "polling_active": True}),
  ):
    active = asyncio.run(intel_source_feed_active(session, "fomo"))
  assert active is True
