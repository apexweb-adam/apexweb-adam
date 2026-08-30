"""Persist session-open burst scans and auto-entries for CRM verification."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.platform_settings import get_platform_setting, set_platform_setting

SESSION_OPEN_EVENTS_KEY = "session_open_events"
MAX_SESSION_OPEN_EVENTS = 30


async def get_session_open_events(session: AsyncSession) -> list[dict[str, Any]]:
  raw = await get_platform_setting(session, SESSION_OPEN_EVENTS_KEY)
  if not raw:
    return []
  try:
    events = json.loads(raw)
  except json.JSONDecodeError:
    return []
  if not isinstance(events, list):
    return []
  return events


async def record_session_open_event(
  session: AsyncSession,
  *,
  bot_type: str,
  event_type: str,
  symbols: list[str] | None = None,
  symbol_count: int | None = None,
  detail: str | None = None,
) -> dict[str, Any]:
  """Append a session-open burst or auto-entry event (newest first)."""
  events = await get_session_open_events(session)
  entry: dict[str, Any] = {
    "timestamp": datetime.utcnow().isoformat(),
    "bot_type": bot_type,
    "event_type": event_type,
    "symbols": symbols or [],
    "symbol_count": symbol_count,
    "detail": detail,
  }
  events.insert(0, entry)
  events = events[:MAX_SESSION_OPEN_EVENTS]
  await set_platform_setting(session, SESSION_OPEN_EVENTS_KEY, json.dumps(events))
  return entry
