"""Tests for manual learning insight application endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_apply_pending_learning_insights_endpoint():
  client = TestClient(app)
  with patch("app.engines.learning_engine.LearningEngine") as mock_cls:
    learner = MagicMock()
    learner.apply_pending_insights = AsyncMock(return_value=2)
    learner.dismiss_noise_insights = AsyncMock(return_value=1)
    mock_cls.return_value = learner
    with patch("app.ws_manager.push_live_update", new_callable=AsyncMock) as push:
      resp = client.post("/api/learning/apply-pending-insights")
  assert resp.status_code == 200
  body = resp.json()
  assert body["status"] == "ok"
  assert body["pending_insights_applied"] == 2
  assert body["noise_insights_dismissed"] == 1
  push.assert_awaited()
