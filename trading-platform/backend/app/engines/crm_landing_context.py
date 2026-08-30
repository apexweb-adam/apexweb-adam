"""Parallel data loading for /crm landing page."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, is_postgres
from app.engines.profitability_gate import ProfitabilityGate

T = TypeVar("T")


async def _with_session(fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
  async with SessionLocal() as session:
    return await fn(session)


async def _safe_session(fn: Callable[[AsyncSession], Awaitable[T]]) -> T | None:
  try:
    return await _with_session(fn)
  except Exception:
    return None


async def _build_crm_landing_context_sequential() -> dict[str, Any]:
  from app.engines.cme_reopen_checklist import build_cme_reopen_checklist
  from app.engines.crm_summary import build_crm_integration_hooks, build_crm_live_snapshot
  from app.engines.intel_source_status import build_intel_sources
  from app.engines.learning_engine import (
    build_crm_content_study_highlights,
    build_crm_learning_highlights,
  )
  from app.engines.scan_preview import build_monday_recovery_summary
  from app.engines.session_open_log import get_session_open_events
  from app.engines.us_stocks_open_checklist import build_us_stocks_open_checklist

  async with SessionLocal() as session:
    gate_engine = ProfitabilityGate(session)
    gate = await gate_engine.evaluate()
    per_bot = await gate_engine.evaluate_per_bot()
    monday_recovery = await build_monday_recovery_summary(session)
    learning = await build_crm_learning_highlights(session)
    content_study = await build_crm_content_study_highlights(session)
    intel_sources = await build_intel_sources(session)
    live_snapshot = await build_crm_live_snapshot(session)
    integrations = await build_crm_integration_hooks(session)
    try:
      session_open_events = await get_session_open_events(session)
    except Exception:
      session_open_events = []
    try:
      cme_checklist = await build_cme_reopen_checklist(session)
    except Exception:
      cme_checklist = None
    try:
      us_stocks_checklist = await build_us_stocks_open_checklist(session)
    except Exception:
      us_stocks_checklist = None

  return {
    "gate": gate,
    "per_bot": per_bot,
    "monday_recovery": monday_recovery,
    "learning": learning,
    "content_study": content_study,
    "intel_sources": intel_sources,
    "live_snapshot": live_snapshot,
    "integrations": integrations,
    "session_open_events": session_open_events,
    "cme_checklist": cme_checklist,
    "us_stocks_checklist": us_stocks_checklist,
  }


async def build_crm_landing_context() -> dict[str, Any]:
  """Load gate, learning, intel, and checklist data for /crm.

  Postgres (production) uses parallel sessions; SQLite falls back to one session
  because concurrent file-backed SQLite connections are unreliable in tests.
  """
  if is_postgres():
    return await _build_crm_landing_context_parallel()
  return await _build_crm_landing_context_sequential()


async def _build_crm_landing_context_parallel() -> dict[str, Any]:
  async def gate_bundle(session: AsyncSession) -> tuple[dict[str, Any], dict[str, Any]]:
    gate_engine = ProfitabilityGate(session)
    gate = await gate_engine.evaluate()
    per_bot = await gate_engine.evaluate_per_bot()
    return gate, per_bot

  from app.engines.cme_reopen_checklist import build_cme_reopen_checklist
  from app.engines.crm_summary import build_crm_integration_hooks, build_crm_live_snapshot
  from app.engines.intel_source_status import build_intel_sources
  from app.engines.learning_engine import (
    build_crm_content_study_highlights,
    build_crm_learning_highlights,
  )
  from app.engines.scan_preview import build_monday_recovery_summary
  from app.engines.session_open_log import get_session_open_events
  from app.engines.us_stocks_open_checklist import build_us_stocks_open_checklist

  (
    gate_data,
    monday_recovery,
    learning,
    content_study,
    intel_sources,
    live_snapshot,
    integrations,
    session_open_events,
    cme_checklist,
    us_stocks_checklist,
  ) = await asyncio.gather(
    _with_session(gate_bundle),
    _with_session(build_monday_recovery_summary),
    _with_session(build_crm_learning_highlights),
    _with_session(build_crm_content_study_highlights),
    _with_session(build_intel_sources),
    _with_session(build_crm_live_snapshot),
    _with_session(build_crm_integration_hooks),
    _safe_session(get_session_open_events),
    _safe_session(build_cme_reopen_checklist),
    _safe_session(build_us_stocks_open_checklist),
  )

  gate, per_bot = gate_data
  return {
    "gate": gate,
    "per_bot": per_bot,
    "monday_recovery": monday_recovery,
    "learning": learning,
    "content_study": content_study,
    "intel_sources": intel_sources,
    "live_snapshot": live_snapshot,
    "integrations": integrations,
    "session_open_events": session_open_events or [],
    "cme_checklist": cme_checklist,
    "us_stocks_checklist": us_stocks_checklist,
  }
