"""Persist session-open burst scans and auto-entries for CRM verification."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.platform_settings import get_platform_setting, set_platform_setting

SESSION_OPEN_EVENTS_KEY = "session_open_events"
PREP_PHASE_STATE_KEY = "prep_phase_state"
MAX_SESSION_OPEN_EVENTS = 30
SESSION_OPEN_BURST_RECOVERY_GRACE_MINUTES = 30


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


async def needs_session_open_burst_recovery(
  session: AsyncSession,
  *,
  bot_type: str,
  session_info: dict[str, Any],
  grace_minutes_after_open: int = SESSION_OPEN_BURST_RECOVERY_GRACE_MINUTES,
) -> bool:
  """True when bot restarted in-session but missed logging burst_scan/auto_entry at open."""
  if not session_info.get("in_session"):
    return False
  since = session_info.get("minutes_since_open")
  if since is None or int(since) > grace_minutes_after_open:
    return False
  open_at = _parse_iso_utc(str(session_info.get("session_open_utc") or ""))
  if open_at is None:
    return False
  events = await get_session_open_events(session)
  for event in events:
    if event.get("bot_type") != bot_type:
      continue
    if event.get("event_type") not in ("burst_scan", "auto_entry"):
      continue
    at = _parse_iso_utc(str(event.get("timestamp") or ""))
    if at is not None and at >= open_at:
      return False
  return True


async def _get_json_setting(session: AsyncSession, key: str) -> Any:
  raw = await get_platform_setting(session, key)
  if not raw:
    return None
  try:
    return json.loads(raw)
  except json.JSONDecodeError:
    return None


async def _set_json_setting(session: AsyncSession, key: str, value: Any) -> None:
  await set_platform_setting(session, key, json.dumps(value))


async def get_prep_phase_state(session: AsyncSession) -> dict[str, Any]:
  state = await _get_json_setting(session, PREP_PHASE_STATE_KEY)
  if isinstance(state, dict):
    return state
  return {}


async def get_session_open_events(session: AsyncSession) -> list[dict[str, Any]]:
  events = await _get_json_setting(session, SESSION_OPEN_EVENTS_KEY)
  if isinstance(events, list):
    return events
  return []


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
  await _set_json_setting(session, SESSION_OPEN_EVENTS_KEY, events)
  return entry


def _queue_delta(previous: list[str], current: list[str]) -> tuple[list[str], list[str]]:
  prev = set(previous)
  curr = set(current)
  return sorted(curr - prev), sorted(prev - curr)


def _format_queue_symbols(event: dict[str, Any], symbols: list[str]) -> str:
  """Include composite scores in queue event detail when available."""
  details = {
    row.get("symbol"): row
    for row in (event.get("open_ready_details") or [])
    if row.get("symbol")
  }
  parts: list[str] = []
  for symbol in symbols:
    row = details.get(symbol) or {}
    composite = row.get("composite")
    if composite is not None:
      parts.append(f"{symbol} ({float(composite):.3f})")
    else:
      parts.append(symbol)
  return ", ".join(parts)


async def monitor_session_prep_transitions(session: AsyncSession) -> list[dict[str, Any]]:
  """Log prep phase changes (fast — no scan preview)."""
  from app.engines.gate_entry_guard import (
    CME_REOPEN_WAKE_MINUTES_AFTER,
    CME_REOPEN_WAKE_MINUTES_BEFORE,
    COMMODITIES_REOPEN_IMMINENT_SCAN_MINUTES,
    STOCKS_OPEN_IMMINENT_SCAN_MINUTES,
    US_OPEN_WAKE_MINUTES_AFTER,
    US_OPEN_WAKE_MINUTES_BEFORE,
    commodities_gate_fast_scan_active,
    commodities_graduation_prep_active,
    commodities_reopen_imminent_scan_active,
    commodities_reopen_wake_active,
    commodities_session_info,
    in_shadow_graduation_nudge,
    session_prep_phase_info,
    stocks_gate_fast_scan_active,
    stocks_open_imminent_scan_active,
    stocks_open_wake_active,
    stocks_session_info,
    stocks_trade_count_graduation_nudge,
  )
  from app.engines.platform_settings import is_bot_paused
  from app.engines.profitability_gate import ProfitabilityGate

  cme_session = commodities_session_info()
  stocks_session = stocks_session_info()
  per_bot = await ProfitabilityGate(session).evaluate_per_bot()
  comm_stats = per_bot.get("commodities") or {}
  stocks_stats = per_bot.get("stocks_futures") or {}
  stocks_shadow = await is_bot_paused(session, "stocks_futures")
  commodities_graduation_nudge = in_shadow_graduation_nudge(
    "commodities",
    comm_stats.get("win_rate"),
    profit_factor=comm_stats.get("profit_factor"),
    total_pnl=comm_stats.get("total_pnl"),
  )
  stocks_trade_count_nudge = stocks_trade_count_graduation_nudge(
    "stocks_futures",
    stocks_shadow,
    stocks_stats.get("win_rate"),
    int(stocks_stats.get("total_trades") or 0),
  )
  prep_state = await get_prep_phase_state(session)
  stocks_open_ready_active = bool(
    (prep_state.get("us_stocks_open") or {}).get("open_ready_symbols")
  )

  tracked = [
    (
      "cme_reopen",
      "commodities",
      session_prep_phase_info(
        session=cme_session,
        imminent_minutes=COMMODITIES_REOPEN_IMMINENT_SCAN_MINUTES,
        wake_minutes_before=CME_REOPEN_WAKE_MINUTES_BEFORE,
        wake_minutes_after=CME_REOPEN_WAKE_MINUTES_AFTER,
        wake_active=commodities_reopen_wake_active(cme_session),
        imminent_active=commodities_reopen_imminent_scan_active(
          cme_session,
          graduation_nudge=commodities_graduation_nudge,
        ),
      ),
      "15s" if commodities_gate_fast_scan_active(
        cme_session,
        graduation_nudge=commodities_graduation_nudge,
      ) else "30s",
    ),
    (
      "us_stocks_open",
      "stocks_futures",
      session_prep_phase_info(
        session=stocks_session,
        imminent_minutes=STOCKS_OPEN_IMMINENT_SCAN_MINUTES,
        wake_minutes_before=US_OPEN_WAKE_MINUTES_BEFORE,
        wake_minutes_after=US_OPEN_WAKE_MINUTES_AFTER,
        wake_active=stocks_open_wake_active(stocks_session),
        imminent_active=stocks_open_imminent_scan_active(
          stocks_session,
          trade_count_nudge=stocks_trade_count_nudge,
          open_ready_active=stocks_open_ready_active,
        ),
      ),
      "15s" if stocks_gate_fast_scan_active(
        stocks_session,
        trade_count_nudge=stocks_trade_count_nudge,
        open_ready_active=stocks_open_ready_active,
      ) else "30s",
    ),
  ]

  state = prep_state
  logged: list[dict[str, Any]] = []

  for session_key, bot_type, phase_info, scan_default in tracked:
    phase = phase_info.get("prep_phase") or "extended"
    scan_label = "5s" if phase == "imminent" else scan_default
    entry_state = state.get(session_key) if isinstance(state.get(session_key), dict) else {}
    prev_phase = entry_state.get("prep_phase")
    if prev_phase and prev_phase != phase:
      logged.append(
        await record_session_open_event(
          session,
          bot_type=bot_type,
          event_type="prep_phase",
          detail=f"{session_key}: {prev_phase} → {phase} (prep scan {scan_label})",
        )
      )
    if not prev_phase:
      state[session_key] = {**entry_state, "prep_phase": phase}
    else:
      state.setdefault(session_key, {})["prep_phase"] = phase

  await _set_json_setting(session, PREP_PHASE_STATE_KEY, state)
  return logged


def _extended_watch_symbols_from_events(
  events: list[dict[str, Any]],
  *,
  bot_type: str,
) -> list[str]:
  symbols: set[str] = set()
  for event in events:
    if event.get("bot_type") != bot_type:
      continue
    if event.get("event_type") == "queue_add":
      symbols.update(event.get("symbols") or [])
  return sorted(symbols)


async def monitor_open_ready_queue(session: AsyncSession) -> list[dict[str, Any]]:
  """Log open-ready and near-floor queue changes (uses scan preview)."""
  from app.engines.gate_entry_guard import (
    build_next_session_events,
    build_session_prep_status,
    commodities_session_info,
    stocks_session_info,
  )
  from app.engines.scan_preview import build_monday_recovery_summary

  monday_recovery = await build_monday_recovery_summary(session)
  cme_session = commodities_session_info()
  stocks_session = stocks_session_info()
  session_prep = build_session_prep_status(
    stocks_session=stocks_session,
    commodities_session=cme_session,
    stocks_trade_count_nudge=bool(monday_recovery.get("stocks_trade_count_nudge")),
    commodities_graduation_nudge=bool(monday_recovery.get("commodities_graduation_nudge")),
    open_ready_rows=monday_recovery.get("open_ready"),
    near_floor_rows=monday_recovery.get("near_floor"),
  )
  next_events = build_next_session_events(
    session_prep=session_prep,
    commodities_session=cme_session,
    stocks_session=stocks_session,
  )

  tracked = [
    ("cme_reopen", "commodities", next_events.get("cme_reopen") or {}),
    ("us_stocks_open", "stocks_futures", next_events.get("us_stocks_open") or {}),
  ]
  state = await get_prep_phase_state(session)
  logged: list[dict[str, Any]] = []
  session_events = await get_session_open_events(session)

  for session_key, bot_type, event in tracked:
    ready = list(event.get("open_ready_symbols") or [])
    near_floor = list(event.get("near_floor_symbols") or [])
    entry_state = state.get(session_key) if isinstance(state.get(session_key), dict) else {}

    prev_ready = list(entry_state.get("open_ready_symbols") or [])
    prev_extended = list(entry_state.get("extended_watch_symbols") or [])
    if not prev_extended:
      prev_extended = _extended_watch_symbols_from_events(session_events, bot_type=bot_type)
    if "open_ready_symbols" not in entry_state:
      if ready:
        logged.append(
          await record_session_open_event(
            session,
            bot_type=bot_type,
            event_type="queue_add",
            symbols=ready,
            detail=f"{session_key}: auto-entry queued — {_format_queue_symbols(event, ready)}",
          )
        )
      state[session_key] = {
        **entry_state,
        "open_ready_symbols": ready,
        "near_floor_symbols": near_floor,
        "extended_watch_symbols": sorted(set(prev_extended) | set(ready)),
        "open_ready_composites": {
          str(row.get("symbol")): row.get("composite")
          for row in (event.get("open_ready_details") or [])
          if row.get("symbol") is not None and row.get("composite") is not None
        },
      }
      continue

    added, removed = _queue_delta(prev_ready, ready)
    if added:
      logged.append(
        await record_session_open_event(
          session,
          bot_type=bot_type,
          event_type="queue_add",
          symbols=added,
          detail=f"{session_key}: auto-entry queued — {_format_queue_symbols(event, added)}",
        )
      )
    if removed:
      prev_composites = entry_state.get("open_ready_composites") or {}
      details_map = {
        str(row.get("symbol")): row.get("composite")
        for row in (event.get("open_ready_details") or [])
        if row.get("symbol")
      }
      remove_parts: list[str] = []
      for symbol in removed:
        composite = details_map.get(symbol)
        if composite is None:
          composite = prev_composites.get(symbol)
        if composite is not None:
          remove_parts.append(f"{symbol} (last {float(composite):.3f})")
        else:
          remove_parts.append(symbol)
      logged.append(
        await record_session_open_event(
          session,
          bot_type=bot_type,
          event_type="queue_remove",
          symbols=removed,
          detail=f"{session_key}: removed from queue — {', '.join(remove_parts)}",
        )
      )

    prev_near = list(entry_state.get("near_floor_symbols") or [])
    near_added, near_removed = _queue_delta(prev_near, near_floor)
    if near_added:
      logged.append(
        await record_session_open_event(
          session,
          bot_type=bot_type,
          event_type="near_floor",
          symbols=near_added,
          detail=f"{session_key}: near composite floor — {', '.join(near_added)}",
        )
      )
    if near_removed:
      logged.append(
        await record_session_open_event(
          session,
          bot_type=bot_type,
          event_type="near_floor_clear",
          symbols=near_removed,
          detail=f"{session_key}: left near-floor watch — {', '.join(near_removed)}",
        )
      )

    details_map = {
      str(row.get("symbol")): row.get("composite")
      for row in (event.get("open_ready_details") or [])
      if row.get("symbol") is not None and row.get("composite") is not None
    }
    state[session_key] = {
      **entry_state,
      "open_ready_symbols": ready,
      "near_floor_symbols": near_floor,
      "extended_watch_symbols": sorted(set(prev_extended) | set(ready) | set(added)),
      "open_ready_composites": {
        **(entry_state.get("open_ready_composites") or {}),
        **details_map,
      },
    }

  await _set_json_setting(session, PREP_PHASE_STATE_KEY, state)
  return logged


async def backfill_open_ready_queue_events(session: AsyncSession) -> list[dict[str, Any]]:
  """Log queue_add for open-ready symbols not yet recorded in session events."""
  from app.engines.gate_entry_guard import (
    build_next_session_events,
    build_session_prep_status,
    commodities_session_info,
    stocks_session_info,
  )
  from app.engines.scan_preview import build_monday_recovery_summary

  monday_recovery = await build_monday_recovery_summary(session)
  cme_session = commodities_session_info()
  stocks_session = stocks_session_info()
  session_prep = build_session_prep_status(
    stocks_session=stocks_session,
    commodities_session=cme_session,
    stocks_trade_count_nudge=bool(monday_recovery.get("stocks_trade_count_nudge")),
    commodities_graduation_nudge=bool(monday_recovery.get("commodities_graduation_nudge")),
    open_ready_rows=monday_recovery.get("open_ready"),
    near_floor_rows=monday_recovery.get("near_floor"),
  )
  next_events = build_next_session_events(
    session_prep=session_prep,
    commodities_session=cme_session,
    stocks_session=stocks_session,
  )

  logged_symbols: set[str] = set()
  for evt in await get_session_open_events(session):
    if evt.get("event_type") == "queue_add":
      logged_symbols.update(evt.get("symbols") or [])

  tracked = [
    ("cme_reopen", "commodities", next_events.get("cme_reopen") or {}),
    ("us_stocks_open", "stocks_futures", next_events.get("us_stocks_open") or {}),
  ]
  logged: list[dict[str, Any]] = []
  for session_key, bot_type, event in tracked:
    ready = list(event.get("open_ready_symbols") or [])
    missing = [symbol for symbol in ready if symbol not in logged_symbols]
    if not missing:
      continue
    logged.append(
      await record_session_open_event(
        session,
        bot_type=bot_type,
        event_type="queue_add",
        symbols=missing,
        detail=f"{session_key}: auto-entry queued — {_format_queue_symbols(event, missing)}",
      )
    )
    logged_symbols.update(missing)
  return logged
