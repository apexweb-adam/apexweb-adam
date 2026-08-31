"""Tests for learning insight serialization."""

from datetime import datetime

from app.engines.learning_engine import serialize_learning_insight
from app.models.entities import LearningInsight


def test_serialize_learning_insight_includes_source_label():
  insight = LearningInsight(
    id=7,
    source_type="wallet_tracker",
    source_title="Whale accumulation on PEPE",
    source_url="https://example.com/pepe",
    key_takeaways="follow wallet intel",
    strategy_impact="crypto bot: increase sentiment weight",
    confidence=0.82,
    applied=True,
    created_at=datetime(2026, 8, 31, 20, 0, 0),
  )

  payload = serialize_learning_insight(insight)

  assert payload["source_type"] == "wallet_tracker"
  assert payload["source_label"] == "Whale"
  assert payload["source_title"] == "Whale accumulation on PEPE"
  assert payload["applied"] is True
  assert payload["created_at"].startswith("2026-08-31")
