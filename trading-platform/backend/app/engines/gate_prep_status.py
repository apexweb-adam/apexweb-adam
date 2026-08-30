"""Cached gate prep status for /api/gate/prep-status — reuses Monday recovery cache."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.gate_entry_guard import (
  build_next_session_events,
  build_session_prep_status,
  commodities_session_info,
  stocks_session_info,
)
from app.engines.scan_preview import build_monday_recovery_summary

GATE_PREP_STATUS_CACHE_TTL_SECONDS = 45
GATE_PREP_STATUS_PREP_CACHE_TTL_SECONDS = 60
_gate_prep_cache: dict[str, Any] | None = None
_gate_prep_cached_at: float = 0.0


def _gate_prep_status_cache_ttl_seconds() -> int:
  """Longer cache during CME weekend prep when prep-status is polled heavily."""
  from app.engines.gate_entry_guard import commodities_futures_weekend_closed

  if commodities_futures_weekend_closed():
    return GATE_PREP_STATUS_PREP_CACHE_TTL_SECONDS
  return GATE_PREP_STATUS_CACHE_TTL_SECONDS


def clear_gate_prep_status_cache() -> None:
  global _gate_prep_cache, _gate_prep_cached_at
  _gate_prep_cache = None
  _gate_prep_cached_at = 0.0


async def build_gate_prep_status(session: AsyncSession) -> dict[str, Any]:
  global _gate_prep_cache, _gate_prep_cached_at
  now = time.monotonic()
  if (
    _gate_prep_cache is not None
    and (now - _gate_prep_cached_at) < _gate_prep_status_cache_ttl_seconds()
  ):
    cached = dict(_gate_prep_cache)
    cached["timestamp"] = datetime.utcnow().isoformat()
    cached["prep_cache_hit"] = True
    cached["prep_cache_age_seconds"] = round(now - _gate_prep_cached_at, 1)
    return cached

  result = await _build_gate_prep_status_uncached(session)
  _gate_prep_cache = result
  _gate_prep_cached_at = now
  result["prep_cache_hit"] = False
  result["prep_cache_age_seconds"] = 0.0
  return result


async def _build_gate_prep_status_uncached(session: AsyncSession) -> dict[str, Any]:
  recovery = await build_monday_recovery_summary(session)
  cme_session = commodities_session_info()
  stocks_session = stocks_session_info()
  session_prep = build_session_prep_status(
    stocks_session=stocks_session,
    commodities_session=cme_session,
    stocks_trade_count_nudge=bool(recovery.get("stocks_trade_count_nudge")),
    commodities_graduation_nudge=bool(recovery.get("commodities_graduation_nudge")),
    open_ready_rows=recovery.get("open_ready"),
    near_floor_rows=recovery.get("near_floor"),
  )
  next_session_events = build_next_session_events(
    session_prep=session_prep,
    commodities_session=cme_session,
    stocks_session=stocks_session,
  )
  return {
    **session_prep,
    "next_session_events": next_session_events,
    "timestamp": datetime.utcnow().isoformat(),
  }
