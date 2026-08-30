"""Compact session-open checklist summaries for /api/status and WebSocket."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


def format_checklist_queue_summary(
  open_ready: dict[str, Any],
  near_floor: dict[str, Any] | None = None,
) -> str:
  """Human-readable queue line for CRM cards and ops scripts."""
  symbols = ", ".join(open_ready.get("symbols") or []) or "—"
  floor = open_ready.get("composite_floor")
  floor_label = f"{float(floor):.2f}" if floor is not None else "?"
  parts = [f"Auto-entry queued: {symbols} · composite floor {floor_label}"]

  sticky = open_ready.get("sticky_symbols") or []
  if sticky:
    margin = open_ready.get("release_margin")
    margin_label = f" ±{margin}" if margin is not None else ""
    parts.append(f"sticky {', '.join(sticky)}{margin_label}")

  near = near_floor or {}
  near_syms = near.get("symbols") or []
  if near_syms:
    gap_bits: list[str] = []
    for row in near.get("details") or []:
      sym = row.get("symbol")
      gap = row.get("gap_to_floor")
      if sym and gap is not None:
        gap_bits.append(f"{sym} +{gap}")
      elif sym:
        gap_bits.append(str(sym))
    near_label = ", ".join(gap_bits) if gap_bits else ", ".join(near_syms)
    parts.append(f"near floor {near_label}")

  return " · ".join(parts)


def summarize_session_open_checklist(checklist: dict[str, Any]) -> dict[str, Any]:
  checks = checklist.get("checks") or []
  open_ready = checklist.get("open_ready") or {}
  near_floor = checklist.get("near_floor") or {}
  events = checklist.get("session_open_events") or {}
  return {
    "ready": bool(checklist.get("ready")),
    "phase": checklist.get("phase"),
    "prep_phase": checklist.get("prep_phase"),
    "minutes_until_open": checklist.get("minutes_until_open"),
    "open_ready_symbols": list(open_ready.get("symbols") or []),
    "near_floor_symbols": list(near_floor.get("symbols") or []),
    "near_floor_gaps": {
      str(row.get("symbol")): row.get("gap_to_floor")
      for row in (near_floor.get("details") or [])
      if row.get("symbol") and row.get("gap_to_floor") is not None
    },
    "sticky_symbols": list(open_ready.get("sticky_symbols") or []),
    "open_ready_composites": {
      str(row.get("symbol")): row.get("composite")
      for row in (open_ready.get("details") or [])
      if row.get("symbol") and row.get("composite") is not None
    },
    "auto_entry_queued": bool(open_ready.get("auto_entry_queued")),
    "composite_floor": open_ready.get("composite_floor"),
    "release_margin": open_ready.get("release_margin"),
    "critical_failures": [
      str(c.get("id"))
      for c in checks
      if c.get("critical") and c.get("status") == "fail"
    ],
    "has_burst_scan": bool(events.get("has_burst_scan")),
    "has_auto_entry": bool(events.get("has_auto_entry")),
  }


async def build_session_open_checklist_summaries(session: AsyncSession) -> dict[str, Any]:
  from app.engines.cme_reopen_checklist import build_cme_reopen_checklist
  from app.engines.us_stocks_open_checklist import build_us_stocks_open_checklist

  cme = await build_cme_reopen_checklist(session)
  us = await build_us_stocks_open_checklist(session)
  return {
    "cme_reopen": summarize_session_open_checklist(cme),
    "us_stocks_open": summarize_session_open_checklist(us),
  }
