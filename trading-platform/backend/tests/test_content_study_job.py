"""Tests for scheduled content study applying pending insights."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.workers.scheduler import content_study_job


def test_content_study_job_applies_pending_insights():
  study_engine = MagicMock()
  study_engine.study_and_apply = AsyncMock(return_value=1)
  study_engine.study_from_intelligence = AsyncMock(return_value=2)

  learner = MagicMock()
  learner.dismiss_noise_insights = AsyncMock(return_value=1)
  learner.apply_pending_insights = AsyncMock(return_value=3)

  session_ctx = MagicMock()
  session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
  session_ctx.__aexit__ = AsyncMock(return_value=None)

  with patch("app.workers.scheduler.SessionLocal", return_value=session_ctx):
    with patch("app.workers.scheduler.ContentStudyEngine", return_value=study_engine):
      with patch("app.workers.scheduler.LearningEngine", return_value=learner):
        with patch("app.ws_manager.push_live_update", new_callable=AsyncMock) as push:
          asyncio.run(content_study_job())

  learner.dismiss_noise_insights.assert_awaited_once()
  learner.apply_pending_insights.assert_awaited_once_with(min_confidence=0.55)
  push.assert_awaited_once()
