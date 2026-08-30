"""Aggregate CME Sunday reopen readiness for CRM and verification scripts."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

CheckStatus = Literal["pass", "fail", "warn", "skip"]


def _check(
  check_id: str,
  status: CheckStatus,
  message: str,
  *,
  critical: bool = True,
) -> dict[str, Any]:
  return {
    "id": check_id,
    "status": status,
    "message": message,
    "critical": critical,
  }


def _overall_ready(checks: list[dict[str, Any]]) -> bool:
  for row in checks:
    if not row.get("critical"):
      continue
    if row.get("status") == "fail":
      return False
  return True


def _checklist_phase(
  *,
  minutes_until_open: int | None,
  in_session: bool,
  has_burst_scan: bool,
  has_auto_entry: bool,
) -> str:
  if has_auto_entry or has_burst_scan:
    return "post_open"
  if in_session:
    return "open"
  if minutes_until_open is not None and minutes_until_open <= 30:
    return "imminent"
  return "preflight"


def build_cme_reopen_checks(
  *,
  platform_revision_current: bool | None,
  minutes_until_open: int | None,
  prep_phase: str | None,
  in_session: bool,
  auto_entry_queued: bool,
  open_ready_symbols: list[str],
  near_floor_symbols: list[str],
  commodities_paused: bool,
  bots_running: int,
  has_burst_scan: bool,
  has_auto_entry: bool,
  composite_floor: float | None,
  open_ready_below_floor: list[str],
  phase: str,
) -> list[dict[str, Any]]:
  checks: list[dict[str, Any]] = []

  if phase == "post_open":
    checks.append(
      _check(
        "burst_scan_logged",
        "pass" if has_burst_scan else "fail",
        "Session-open burst scan recorded in session_open_events"
        if has_burst_scan
        else "No burst_scan event yet — commodities bot may not have scanned at open",
      )
    )
    if open_ready_symbols:
      checks.append(
        _check(
          "auto_entry_logged",
          "pass" if has_auto_entry else "warn",
          "Gate-skip auto-entry recorded"
          if has_auto_entry
          else "No auto_entry yet — signals may have weakened below floor at open",
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
        "warn" if minutes_until_open and minutes_until_open > 360 else "fail",
        "Platform revision behind expected — deploy before CME for burst ordering and logging",
        critical=bool(minutes_until_open is not None and minutes_until_open <= 360),
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

  if commodities_paused:
    checks.append(
      _check(
        "commodities_active",
        "fail",
        "Commodities bot is paused — auto-entry will not fire",
      )
    )
  else:
    checks.append(
      _check(
        "commodities_active",
        "pass",
        "Commodities bot active",
      )
    )

  if prep_phase in ("extended", "imminent", "wake", "open"):
    checks.append(
      _check(
        "prep_phase",
        "pass",
        f"CME prep phase is {prep_phase}",
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
        "No open-ready symbols queued for CME auto-entry",
        critical=False,
      )
    )

  if open_ready_below_floor:
    floor_label = f"{composite_floor:.2f}" if composite_floor is not None else "?"
    checks.append(
      _check(
        "composite_floor",
        "fail",
        f"Queued symbols below composite floor ({floor_label}): {', '.join(open_ready_below_floor)}",
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
        "cme_session",
        "pass",
        "CME futures session is open",
      )
    )
  elif minutes_until_open is not None:
    checks.append(
      _check(
        "cme_session",
        "pass",
        f"CME reopen in {minutes_until_open} minutes",
        critical=False,
      )
    )

  return checks


def _symbols_below_floor(
  open_ready_details: list[dict[str, Any]],
  composite_floor: float | None,
  *,
  release_margin: float = 0.02,
) -> list[str]:
  if composite_floor is None:
    return []
  below: list[str] = []
  for row in open_ready_details:
    symbol = row.get("symbol")
    composite = row.get("composite")
    if not symbol or composite is None:
      continue
    effective_floor = composite_floor
    if row.get("sticky_queue"):
      effective_floor = composite_floor - release_margin
    if float(composite) < effective_floor:
      below.append(str(symbol))
  return below


def _recent_commodities_events(
  events: list[dict[str, Any]],
  *,
  event_types: set[str] | None = None,
) -> list[dict[str, Any]]:
  filtered: list[dict[str, Any]] = []
  for event in events:
    if event.get("bot_type") != "commodities":
      continue
    if event_types and event.get("event_type") not in event_types:
      continue
    filtered.append(event)
  return filtered


async def build_cme_reopen_checklist(session: AsyncSession) -> dict[str, Any]:
  """Single JSON payload for CME reopen preflight and post-open verification."""
  from app.engines.deploy_status import (
    EXPECTED_PLATFORM_REVISION,
    build_cme_deploy_urgency,
    build_deploy_status,
  )
  from app.engines.gate_entry_guard import (
    OPEN_READY_QUEUE_RELEASE_MARGIN,
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
  cme = next_events.get("cme_reopen") or {}
  commodities_prep = session_prep.get("commodities") or {}

  platform_revision = os.environ.get("PLATFORM_REVISION", "").strip() or None
  deploy_info = await build_deploy_status()
  revision_current = (
    platform_revision == EXPECTED_PLATFORM_REVISION if platform_revision else None
  )
  deploy_urgency = build_cme_deploy_urgency(
    platform_revision_current=revision_current,
    cme_minutes_until_open=cme.get("minutes_until_open"),
    cme_in_session=bool(cme_session.get("in_session")),
  )

  per_bot = await ProfitabilityGate(session).evaluate_per_bot()
  comm_gate = per_bot.get("commodities") or {}
  commodities_paused = await is_bot_paused(session, "commodities")

  from app.models import BotState
  from sqlalchemy import select

  bot_states = (await session.execute(select(BotState))).scalars().all()
  bots_running = sum(1 for state in bot_states if state.status == "running")

  all_events = await get_session_open_events(session)
  commodities_events = _recent_commodities_events(all_events)
  burst_events = _recent_commodities_events(all_events, event_types={"burst_scan"})
  auto_entry_events = _recent_commodities_events(all_events, event_types={"auto_entry"})
  has_burst_scan = bool(burst_events)
  has_auto_entry = bool(auto_entry_events)

  open_ready_symbols = list(cme.get("open_ready_symbols") or [])
  open_ready_details = list(cme.get("open_ready_details") or [])
  near_floor_symbols = list(cme.get("near_floor_symbols") or [])
  composite_floor = cme.get("composite_floor")
  floor_value = float(composite_floor) if composite_floor is not None else None
  below_floor = _symbols_below_floor(
    open_ready_details,
    floor_value,
    release_margin=OPEN_READY_QUEUE_RELEASE_MARGIN,
  )

  minutes_until_open = cme.get("minutes_until_open")
  prep_phase = cme.get("prep_phase") or commodities_prep.get("prep_phase")
  in_session = bool(cme_session.get("in_session"))
  phase = _checklist_phase(
    minutes_until_open=minutes_until_open,
    in_session=in_session,
    has_burst_scan=has_burst_scan,
    has_auto_entry=has_auto_entry,
  )

  checks = build_cme_reopen_checks(
    platform_revision_current=revision_current,
    minutes_until_open=minutes_until_open,
    prep_phase=prep_phase,
    in_session=in_session,
    auto_entry_queued=bool(cme.get("auto_entry_queued")),
    open_ready_symbols=open_ready_symbols,
    near_floor_symbols=near_floor_symbols,
    commodities_paused=commodities_paused,
    bots_running=bots_running,
    has_burst_scan=has_burst_scan,
    has_auto_entry=has_auto_entry,
    composite_floor=floor_value,
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
      "cme_deploy_urgency": deploy_urgency,
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
      "auto_entry_queued": bool(cme.get("auto_entry_queued")),
      "composite_floor": composite_floor,
      "release_margin": OPEN_READY_QUEUE_RELEASE_MARGIN,
    },
    "near_floor": {
      "symbols": near_floor_symbols,
      "details": cme.get("near_floor_details") or [],
    },
    "gate": {
      "commodities_paused": commodities_paused,
      "win_rate": comm_gate.get("win_rate"),
      "profit_factor": comm_gate.get("profit_factor"),
      "total_pnl": comm_gate.get("total_pnl"),
    },
    "session_open_events": {
      "recent": commodities_events[:10],
      "has_burst_scan": has_burst_scan,
      "has_auto_entry": has_auto_entry,
      "latest_burst_scan": burst_events[0] if burst_events else None,
      "latest_auto_entry": auto_entry_events[0] if auto_entry_events else None,
    },
    "checks": checks,
  }


_CHECK_STATUS_COLORS = {
  "pass": "#4ade80",
  "fail": "#f87171",
  "warn": "#fbbf24",
  "skip": "#888",
}


def should_show_cme_checklist_on_crm(checklist: dict[str, Any] | None) -> bool:
  if not checklist:
    return False
  if checklist.get("minutes_until_open") is not None:
    return True
  if checklist.get("phase") in ("open", "post_open"):
    return True
  open_ready = checklist.get("open_ready") or {}
  near_floor = checklist.get("near_floor") or {}
  return bool(open_ready.get("symbols") or near_floor.get("symbols"))


def format_cme_checklist_crm_html(checklist: dict[str, Any]) -> str:
  """Render checklist checks for the /crm landing page."""
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

  return f"""<div class="card" style="border-color:#1e3a5f;background:#0c1929;">
    <h2 style="color:#60a5fa;">CME reopen checklist</h2>
    <p class="muted" style="margin-top:0;">Phase <strong>{phase}</strong> ·
      <span style="color:{ready_color};font-weight:600;">{ready_label}</span>
      · open in {countdown}</p>
    <p class="muted" style="margin-top:0;">{queue_summary}
      · <a href="/api/gate/cme-reopen-checklist">JSON API</a></p>
    <table>
      <thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>"""
