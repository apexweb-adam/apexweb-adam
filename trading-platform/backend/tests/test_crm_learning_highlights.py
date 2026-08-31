"""Tests for CRM learning loop highlight builders."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.engines.learning_engine import (
  build_crm_content_study_highlights,
  build_crm_learning_highlights,
)
from app.models.entities import DailyReview, LearningInsight


def test_build_crm_learning_highlights_includes_active_reviews():
  review = DailyReview(
    bot_type="crypto",
    review_date=datetime.utcnow().strftime("%Y-%m-%d"),
    total_trades=4,
    losing_trades=2,
    total_loss=-3.0,
    total_profit=1.5,
    net_pnl=-1.5,
    win_rate=0.5,
    patterns_found="2 losses had weak signals",
    conclusions="Below target win rate",
    strategy_changes="Raised minimum signal score",
  )
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[review]))))
  )
  session.scalar = AsyncMock(side_effect=[12, 3])

  highlights = asyncio.run(build_crm_learning_highlights(session))

  assert highlights["trade_analyses"] == 12
  assert highlights["pending_insights"] == 3
  assert len(highlights["reviews"]) == 1
  assert highlights["reviews"][0]["bot_type"] == "crypto"
  assert "weak signals" in highlights["reviews"][0]["patterns_found"]


def test_build_crm_learning_highlights_skips_empty_reviews():
  review = DailyReview(
    bot_type="polymarket",
    review_date=datetime.utcnow().strftime("%Y-%m-%d"),
    total_trades=0,
    losing_trades=0,
    total_loss=0.0,
    total_profit=0.0,
    net_pnl=0.0,
    win_rate=0.0,
    patterns_found="",
    conclusions="",
    strategy_changes="",
  )
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[review]))))
  )
  session.scalar = AsyncMock(side_effect=[0, 0])

  highlights = asyncio.run(build_crm_learning_highlights(session))

  assert highlights["reviews"] == []


def test_collect_intel_pattern_alerts_extracts_confirmation_lines():
  from app.engines.learning_engine import collect_intel_pattern_alerts

  patterns = (
    "2 losses had weak signals (<0.5); "
    "2 losses tied to TikTok/social hype — tighten intel confirmation gates"
  )
  alerts = collect_intel_pattern_alerts(patterns)
  assert len(alerts) == 1
  assert "tiktok" in alerts[0].lower()
  assert "intel confirmation" in alerts[0].lower()


def test_build_crm_learning_highlights_includes_intel_pattern_alerts():
  review = DailyReview(
    bot_type="crypto",
    review_date=datetime.utcnow().strftime("%Y-%m-%d"),
    total_trades=3,
    losing_trades=2,
    total_loss=-2.0,
    total_profit=0.5,
    net_pnl=-1.5,
    win_rate=0.33,
    patterns_found="2 losses tied to Reddit retail buzz — tighten intel confirmation gates",
    conclusions="Below target win rate",
    strategy_changes="Tightened intel confirmation gates",
  )
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[review]))))
  )
  session.scalar = AsyncMock(side_effect=[4, 1])

  highlights = asyncio.run(build_crm_learning_highlights(session))

  assert highlights["intel_pattern_alerts"] == [
    "crypto: 2 losses tied to Reddit retail buzz — tighten intel confirmation gates"
  ]


def test_fetch_learning_counts_includes_intel_pattern_alerts():
  from app.engines.platform_status import _fetch_learning_counts

  def count_result(value: int):
    return MagicMock(scalar_one=MagicMock(return_value=value))

  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      count_result(8),
      count_result(3),
      count_result(12),
      count_result(9),
      count_result(2),
      MagicMock(
        all=MagicMock(
          return_value=[
            ("crypto", "2 losses tied to TikTok/social hype — tighten intel confirmation gates"),
          ]
        )
      ),
    ]
  )

  counts = asyncio.run(_fetch_learning_counts(session))

  assert counts["intel_pattern_count"] == 1
  assert "crypto:" in counts["intel_pattern_alerts"][0]
  assert "tiktok" in counts["intel_pattern_alerts"][0].lower()


def test_build_crm_content_study_highlights_truncates_long_fields():
  insight = LearningInsight(
    source_type="youtube",
    source_title="A" * 90,
    source_url="https://example.com/video",
    key_takeaways="takeaways",
    strategy_impact="B" * 150,
    confidence=0.82,
    applied=True,
  )
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[insight]))))
  )
  session.scalar = AsyncMock(return_value=5)

  highlights = asyncio.run(build_crm_content_study_highlights(session))

  assert highlights["insights_applied"] == 5
  assert len(highlights["recent"]) == 1
  assert highlights["recent"][0]["title"].endswith("…")
  assert highlights["recent"][0]["impact"].endswith("…")
  assert highlights["recent"][0]["applied"] is True
