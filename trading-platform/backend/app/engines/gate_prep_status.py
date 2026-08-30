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


def gate_prep_status_cache_age_seconds() -> float | None:
  if _gate_prep_cache is None:
    return None
  return round(time.monotonic() - _gate_prep_cached_at, 1)


def gate_prep_status_cache_fresh(max_age_seconds: float) -> bool:
  age = gate_prep_status_cache_age_seconds()
  return age is not None and age < max_age_seconds


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
    **_enrich_prep_with_session_events(session_prep, next_session_events),
    "next_session_events": next_session_events,
    "timestamp": datetime.utcnow().isoformat(),
  }


def _enrich_prep_with_session_events(
  session_prep: dict[str, Any],
  next_session_events: dict[str, Any],
) -> dict[str, Any]:
  """Surface auto-entry fields on each bot prep entry for lightweight CRM polls."""
  enriched = dict(session_prep)
  cme = next_session_events.get("cme_reopen") or {}
  us = next_session_events.get("us_stocks_open") or {}
  commodities = dict(enriched.get("commodities") or {})
  stocks = dict(enriched.get("stocks_futures") or {})
  commodities.update(
    {
      "auto_entry_queued": bool(cme.get("auto_entry_queued")),
      "composite_floor": cme.get("composite_floor"),
      "open_ready_symbols": cme.get("open_ready_symbols") or commodities.get("open_ready_symbols"),
      "open_ready_details": cme.get("open_ready_details") or commodities.get("open_ready_details"),
      "near_floor_symbols": cme.get("near_floor_symbols") or commodities.get("near_floor_symbols"),
      "near_floor_details": cme.get("near_floor_details") or commodities.get("near_floor_details"),
    }
  )
  stocks.update(
    {
      "auto_entry_queued": bool(us.get("auto_entry_queued")),
      "open_ready_symbols": us.get("open_ready_symbols") or stocks.get("open_ready_symbols"),
      "open_ready_details": us.get("open_ready_details") or stocks.get("open_ready_details"),
      "near_floor_symbols": us.get("near_floor_symbols") or stocks.get("near_floor_symbols"),
      "near_floor_details": us.get("near_floor_details") or stocks.get("near_floor_details"),
    }
  )
  enriched["commodities"] = commodities
  enriched["stocks_futures"] = stocks
  return enriched
