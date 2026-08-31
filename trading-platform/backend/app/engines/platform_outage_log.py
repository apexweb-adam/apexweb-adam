"""Detect and log platform downtime gaps (e.g. Render billing suspension) for learning."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.platform_settings import get_platform_setting, set_platform_setting
from app.engines.session_open_log import get_prep_phase_state, record_session_open_event

PLATFORM_LAST_ONLINE_KEY = "platform_last_online_utc"
PLATFORM_OUTAGE_EVENTS_KEY = "platform_outage_events"
MIN_OUTAGE_GAP_MINUTES = 20
MAX_OUTAGE_EVENTS = 15


def _parse_iso_utc(value: str | None) -> datetime | None:
  if not value:
    return None
  try:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
  except ValueError:
    try:
      return datetime.fromisoformat(value)
    except ValueError:
      return None


async def get_platform_outage_events(session: AsyncSession) -> list[dict[str, Any]]:
  raw = await get_platform_setting(session, PLATFORM_OUTAGE_EVENTS_KEY)
  if not raw:
    return []
  try:
    events = json.loads(raw)
  except json.JSONDecodeError:
    return []
  return events if isinstance(events, list) else []


async def record_platform_online_heartbeat(session: AsyncSession) -> None:
  await set_platform_setting(session, PLATFORM_LAST_ONLINE_KEY, datetime.utcnow().isoformat())


async def detect_and_log_platform_outage(session: AsyncSession) -> dict[str, Any] | None:
  """On startup, log outage if last heartbeat gap exceeds MIN_OUTAGE_GAP_MINUTES."""
  last_raw = await get_platform_setting(session, PLATFORM_LAST_ONLINE_KEY)
  now = datetime.utcnow()
  if not last_raw:
    await record_platform_online_heartbeat(session)
    return None

  last = _parse_iso_utc(last_raw)
  if last is None:
    await record_platform_online_heartbeat(session)
    return None

  gap_minutes = int((now - last).total_seconds() // 60)
  if gap_minutes < MIN_OUTAGE_GAP_MINUTES:
    await record_platform_online_heartbeat(session)
    return None

  from app.engines.gate_entry_guard import commodities_session_info, stocks_session_info

  stocks = stocks_session_info()
  cme = commodities_session_info()
  prep = await get_prep_phase_state(session)
  us_ready = list((prep.get("us_stocks_open") or {}).get("open_ready_symbols") or [])
  cme_ready = list((prep.get("cme_reopen") or {}).get("open_ready_symbols") or [])

  event: dict[str, Any] = {
    "detected_at": now.isoformat(),
    "last_online_utc": last_raw,
    "gap_minutes": gap_minutes,
    "platform_revision": os.environ.get("PLATFORM_REVISION") or None,
    "stocks_in_session": bool(stocks.get("in_session")),
    "stocks_minutes_since_open": stocks.get("minutes_since_open"),
    "cme_in_session": bool(cme.get("in_session")),
    "us_open_ready_symbols": us_ready,
    "cme_open_ready_symbols": cme_ready,
  }

  events = await get_platform_outage_events(session)
  events.insert(0, event)
  events = events[:MAX_OUTAGE_EVENTS]
  await set_platform_setting(session, PLATFORM_OUTAGE_EVENTS_KEY, json.dumps(events))

  detail = (
    f"Platform outage gap {gap_minutes}min — "
    f"US queued={us_ready or 'none'} CME queued={cme_ready or 'none'}"
  )
  if us_ready:
    await record_session_open_event(
      session,
      bot_type="stocks_futures",
      event_type="platform_outage",
      symbols=us_ready,
      detail=detail,
    )
  elif cme_ready:
    await record_session_open_event(
      session,
      bot_type="commodities",
      event_type="platform_outage",
      symbols=cme_ready,
      detail=detail,
    )

  await record_platform_online_heartbeat(session)
  print(f"[PlatformOutage] {detail}")
  return event


async def platform_outage_patterns_for_review(
  session: AsyncSession,
  review_date: str,
) -> list[str]:
  """Patterns for daily review when platform downtime occurred on review_date."""
  patterns: list[str] = []
  for event in await get_platform_outage_events(session):
    detected = str(event.get("detected_at") or "")
    if not detected.startswith(review_date):
      continue
    gap = int(event.get("gap_minutes") or 0)
    us = event.get("us_open_ready_symbols") or []
    cme = event.get("cme_open_ready_symbols") or []
    queued = us or cme
    if queued:
      patterns.append(
        f"Platform downtime {gap}min — missed session open with queued: {', '.join(queued)}"
      )
    elif event.get("stocks_in_session") or event.get("cme_in_session"):
      patterns.append(f"Platform downtime {gap}min — bots offline during active session")
    else:
      patterns.append(f"Platform downtime {gap}min — service was offline")
  return patterns
