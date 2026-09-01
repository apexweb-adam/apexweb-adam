"""Tests for low-confidence learning insight dismissal."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.engines.learning_engine import LearningEngine


def _insight(confidence: float, applied: bool = False):
  return SimpleNamespace(confidence=confidence, applied=applied)


def test_dismiss_noise_marks_low_confidence_applied():
  low = _insight(0.35)
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[low]))))
  )
  session.commit = AsyncMock()

  dismissed = asyncio.run(LearningEngine(session).dismiss_noise_insights(max_confidence=0.5))

  assert dismissed == 1
  assert low.applied is True
  session.commit.assert_awaited_once()


def test_dismiss_noise_skips_when_none_below_threshold():
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
  )
  session.commit = AsyncMock()

  dismissed = asyncio.run(LearningEngine(session).dismiss_noise_insights(max_confidence=0.5))

  assert dismissed == 0
  session.commit.assert_not_awaited()
