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


def test_intel_source_label_covers_all_live_intel_sources():
  from app.engines.learning_engine import intel_source_label
  from app.intelligence.content_study import LIVE_INTEL_SOURCES

  for source in LIVE_INTEL_SOURCES:
    label = intel_source_label(source)
    assert label
    assert label != "unknown"
    assert label != source or source in ("fomo", "axiom")


def test_get_insights_endpoint_includes_source_label():
  from datetime import datetime
  from unittest.mock import AsyncMock, MagicMock

  from fastapi.testclient import TestClient

  from app.database import get_db
  from app.main import app
  from app.models.entities import LearningInsight

  insight = LearningInsight(
    id=3,
    source_type="political",
    source_title="Tariff escalation",
    source_url="https://example.com/tariff",
    key_takeaways="commodities risk-off",
    strategy_impact="commodities bot: tighten sentiment gate",
    confidence=0.8,
    applied=True,
    created_at=datetime(2026, 8, 31, 12, 0, 0),
  )

  scalars = MagicMock()
  scalars.all.return_value = [insight]
  result = MagicMock()
  result.scalars.return_value = scalars
  session = AsyncMock()
  session.execute = AsyncMock(return_value=result)

  async def fake_get_db():
    yield session

  app.dependency_overrides[get_db] = fake_get_db
  try:
    client = TestClient(app)
    resp = client.get("/api/insights?limit=5")
  finally:
    app.dependency_overrides.clear()

  assert resp.status_code == 200
  body = resp.json()
  assert len(body) == 1
  assert body[0]["source_type"] == "political"
  assert body[0]["source_label"] == "Political"
