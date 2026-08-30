"""US stocks Monday open readiness for CRM and verification scripts."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cme_reopen_checklist import (
  _CHECK_STATUS_COLORS,
  _check,
  _checklist_phase,
  _overall_ready,
  _symbols_below_floor,
)


def _recent_bot_events(
  events: list[dict[str, Any]],
  bot_type: str,
  *,
  event_types: set[str] | None = None,
) -> list[dict[str, Any]]:
  filtered: list[dict[str, Any]] = []
  for event in events:
    if event.get("bot_type") != bot_type:
      continue
    if event_types and event.get("event_type") not in event_types:
      continue
    filtered.append(event)
  return filtered


def build_us_stocks_open_checks(
  *,
  platform_revision_current: bool | None,
  minutes_until_open: int | None,
  prep_phase: str | None,
  in_session: bool,
  auto_entry_queued: bool,
  open_ready_symbols: list[str],
  near_floor_symbols: list[str],
  stocks_paused: bool,
  bots_running: int,
  has_burst_scan: bool,
  has_auto_entry: bool,
  open_ready_below_floor: list[str],
  phase: str,
) -> list[dict[str, Any]]:
  checks: list[dict[str, Any]] = []

  if phase == "post_open":
    session_open_logged = has_burst_scan or has_auto_entry
    checks.append(
      _check(
        "burst_scan_logged",
        "pass" if session_open_logged else "fail",
        "US open burst scan recorded in session_open_events"
        if has_burst_scan
        else "US open auto-entry recorded in session_open_events"
        if has_auto_entry
        else "No burst_scan or auto_entry event yet — stocks bot may not have scanned at open",
      )
    )
    if open_ready_symbols:
      checks.append(
        _check(
          "auto_entry_logged",
          "pass" if has_auto_entry else "warn",
          "Gate-skip auto-entry recorded"
          if has_auto_entry
          else "No auto_entry yet — signals may have weakened before open",
          critical=False,
        )
      )
    else:
      checks.append(
        _check(
          "auto_entry_logged",
          "skip",
          "No symbols were queued for auto-entry before open",
          critical=False,
        )
      )
    return checks

  if platform_revision_current is False:
    checks.append(
      _check(
        "deploy_current",
        "warn" if minutes_until_open and minutes_until_open > 720 else "fail",
        "Platform revision behind expected — deploy before US open for session-open logging",
        critical=bool(minutes_until_open is not None and minutes_until_open <= 720),
      )
    )
  else:
    checks.append(
      _check(
        "deploy_current",
        "pass",
        "Platform revision matches expected",
      )
    )

  checks.append(
    _check(
      "backend_health",
      "pass" if bots_running >= 3 else "fail",
      f"{bots_running} bots running (need ≥3)"
      if bots_running >= 3
      else f"Only {bots_running} bots running",
    )
  )

  if stocks_paused:
    checks.append(
      _check(
        "stocks_active",
        "fail",
        "Stocks bot is paused — auto-entry will not fire",
      )
    )
  else:
    checks.append(
      _check(
        "stocks_active",
        "pass",
        "Stocks bot active",
      )
    )

  if prep_phase in ("extended", "imminent", "wake", "open"):
    checks.append(
      _check(
        "prep_phase",
        "pass",
        f"US stocks prep phase is {prep_phase}",
      )
    )
  else:
    checks.append(
      _check(
        "prep_phase",
        "fail",
        f"Unexpected prep phase: {prep_phase}",
      )
    )

  if open_ready_symbols and auto_entry_queued:
    checks.append(
      _check(
        "auto_entry_queued",
        "pass",
        f"Gate-skip auto-entry queued: {', '.join(open_ready_symbols)}",
      )
    )
  elif open_ready_symbols:
    checks.append(
      _check(
        "auto_entry_queued",
        "fail",
        f"Open-ready symbols present but auto_entry_queued is false: {', '.join(open_ready_symbols)}",
      )
    )
  else:
    checks.append(
      _check(
        "auto_entry_queued",
        "warn",
        "No open-ready symbols queued for US open auto-entry",
        critical=False,
      )
    )

  if open_ready_below_floor:
    checks.append(
      _check(
        "composite_floor",
        "fail",
        f"Queued symbols below composite floor: {', '.join(open_ready_below_floor)}",
      )
    )
  elif near_floor_symbols:
    checks.append(
      _check(
        "composite_floor",
        "warn",
        f"Near-floor watch: {', '.join(near_floor_symbols)}",
        critical=False,
      )
    )
  elif open_ready_symbols:
    checks.append(
      _check(
        "composite_floor",
        "pass",
        "All queued symbols above composite floor",
      )
    )

  if in_session:
    checks.append(
      _check(
        "us_stocks_session",
        "pass",
        "US stocks session is open",
      )
    )
  elif minutes_until_open is not None:
    checks.append(
      _check(
        "us_stocks_session",
        "pass",
        f"US stocks open in {minutes_until_open} minutes",
        critical=False,
      )
    )

  return checks


async def build_us_stocks_open_checklist(session: AsyncSession) -> dict[str, Any]:
  """JSON payload for Monday US stocks open preflight and post-open verification."""
  from app.engines.deploy_status import EXPECTED_PLATFORM_REVISION, build_deploy_status
  from app.engines.gate_entry_guard import (
    build_next_session_events,
    build_session_prep_status,
    commodities_session_info,
    stocks_session_info,
  )
  from app.engines.platform_settings import is_bot_paused
  from app.engines.profitability_gate import ProfitabilityGate
  from app.engines.scan_preview import build_monday_recovery_summary
  from app.engines.session_open_log import get_session_open_events

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
  next_events = build_next_session_events(
    session_prep=session_prep,
    commodities_session=cme_session,
    stocks_session=stocks_session,
  )
  us = next_events.get("us_stocks_open") or {}
  stocks_prep = session_prep.get("stocks_futures") or {}

  platform_revision = os.environ.get("PLATFORM_REVISION", "").strip() or None
  deploy_info = await build_deploy_status()
  revision_current = (
    platform_revision == EXPECTED_PLATFORM_REVISION if platform_revision else None
  )

  per_bot = await ProfitabilityGate(session).evaluate_per_bot()
  stocks_gate = per_bot.get("stocks_futures") or {}
  stocks_paused = await is_bot_paused(session, "stocks_futures")

  from app.models import BotState
  from sqlalchemy import select

  bot_states = (await session.execute(select(BotState))).scalars().all()
  bots_running = sum(1 for state in bot_states if state.status == "running")

  all_events = await get_session_open_events(session)
  stocks_events = _recent_bot_events(all_events, "stocks_futures")
  burst_events = _recent_bot_events(all_events, "stocks_futures", event_types={"burst_scan"})
  auto_entry_events = _recent_bot_events(all_events, "stocks_futures", event_types={"auto_entry"})
  has_burst_scan = bool(burst_events)
  has_auto_entry = bool(auto_entry_events)

  open_ready_symbols = list(us.get("open_ready_symbols") or [])
  open_ready_details = list(us.get("open_ready_details") or [])
  near_floor_symbols = list(us.get("near_floor_symbols") or [])
  floor_value = 0.34
  below_floor = _symbols_below_floor(open_ready_details, floor_value)

  minutes_until_open = us.get("minutes_until_open")
  prep_phase = us.get("prep_phase") or stocks_prep.get("prep_phase")
  in_session = bool(stocks_session.get("in_session"))
  phase = _checklist_phase(
    minutes_until_open=minutes_until_open,
    in_session=in_session,
    has_burst_scan=has_burst_scan,
    has_auto_entry=has_auto_entry,
  )

  checks = build_us_stocks_open_checks(
    platform_revision_current=revision_current,
    minutes_until_open=minutes_until_open,
    prep_phase=prep_phase,
    in_session=in_session,
    auto_entry_queued=bool(us.get("auto_entry_queued")),
    open_ready_symbols=open_ready_symbols,
    near_floor_symbols=near_floor_symbols,
    stocks_paused=stocks_paused,
    bots_running=bots_running,
    has_burst_scan=has_burst_scan,
    has_auto_entry=has_auto_entry,
    open_ready_below_floor=below_floor,
    phase=phase,
  )

  return {
    "timestamp": datetime.utcnow().isoformat(),
    "phase": phase,
    "ready": _overall_ready(checks),
    "minutes_until_open": minutes_until_open,
    "prep_phase": prep_phase,
    "in_session": in_session,
    "deploy": {
      "platform_revision": platform_revision or deploy_info.get("platform_revision"),
      "expected_platform_revision": EXPECTED_PLATFORM_REVISION,
      "platform_revision_current": revision_current,
      "deploy_command": "TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh",
    },
    "open_ready": {
      "symbols": open_ready_symbols,
      "details": open_ready_details,
      "sticky_symbols": [
        str(row.get("symbol"))
        for row in open_ready_details
        if row.get("symbol") and row.get("sticky_queue")
      ],
      "auto_entry_queued": bool(us.get("auto_entry_queued")),
      "composite_floor": floor_value,
      "release_margin": 0.02,
    },
    "near_floor": {
      "symbols": near_floor_symbols,
      "details": us.get("near_floor_details") or [],
    },
    "gate": {
      "stocks_paused": stocks_paused,
      "win_rate": stocks_gate.get("win_rate"),
      "profit_factor": stocks_gate.get("profit_factor"),
      "total_pnl": stocks_gate.get("total_pnl"),
    },
    "session_open_events": {
      "recent": stocks_events[:10],
      "has_burst_scan": has_burst_scan,
      "has_auto_entry": has_auto_entry,
      "latest_burst_scan": burst_events[0] if burst_events else None,
      "latest_auto_entry": auto_entry_events[0] if auto_entry_events else None,
    },
    "checks": checks,
  }


def should_show_us_stocks_checklist_on_crm(checklist: dict[str, Any] | None) -> bool:
  if not checklist:
    return False
  open_ready = checklist.get("open_ready") or {}
  near_floor = checklist.get("near_floor") or {}
  if not open_ready.get("symbols") and not near_floor.get("symbols"):
    return False
  mins = checklist.get("minutes_until_open")
  if mins is not None and mins <= 2880:
    return True
  return checklist.get("phase") in ("open", "post_open")


def format_us_stocks_checklist_crm_html(checklist: dict[str, Any]) -> str:
  from app.engines.session_open_checklist_summary import format_checklist_queue_summary

  phase = checklist.get("phase") or "preflight"
  ready = bool(checklist.get("ready"))
  checks = checklist.get("checks") or []
  open_ready = checklist.get("open_ready") or {}
  near_floor = checklist.get("near_floor") or {}
  queue_summary = format_checklist_queue_summary(open_ready, near_floor)
  mins = checklist.get("minutes_until_open")
  countdown = f"{mins // 60}h {mins % 60}m" if mins is not None else "soon"
  ready_color = "#4ade80" if ready else "#fbbf24"
  ready_label = "ready" if ready else "needs attention"

  rows = ""
  for row in checks:
    status = str(row.get("status") or "skip")
    color = _CHECK_STATUS_COLORS.get(status, "#888")
    rows += (
      f"<tr><td>{row.get('id', '')}</td>"
      f"<td style='color:{color}'>{status}</td>"
      f"<td>{row.get('message', '')}</td></tr>"
    )
  if not rows:
    rows = "<tr><td colspan='3' class='muted'>No checks for current phase.</td></tr>"

  return f"""<div class="card" style="border-color:#166534;background:#052e16;">
    <h2 style="color:#4ade80;">US stocks open checklist</h2>
    <p class="muted" style="margin-top:0;">Phase <strong>{phase}</strong> ·
      <span style="color:{ready_color};font-weight:600;">{ready_label}</span>
      · open in {countdown}</p>
    <p class="muted" style="margin-top:0;">{queue_summary}
      · <a href="/api/gate/us-stocks-open-checklist">JSON API</a></p>
    <table>
      <thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>"""
