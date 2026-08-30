"""Compact session-open checklist summaries for /api/status and WebSocket."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


def summarize_session_open_checklist(checklist: dict[str, Any]) -> dict[str, Any]:
  checks = checklist.get("checks") or []
  open_ready = checklist.get("open_ready") or {}
  events = checklist.get("session_open_events") or {}
  return {
    "ready": bool(checklist.get("ready")),
    "phase": checklist.get("phase"),
    "prep_phase": checklist.get("prep_phase"),
    "minutes_until_open": checklist.get("minutes_until_open"),
    "open_ready_symbols": list(open_ready.get("symbols") or []),
    "sticky_symbols": list(open_ready.get("sticky_symbols") or []),
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
