"""Track successful intel scans even when no new items are inserted."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import PlatformSetting

INTEL_SCAN_HEARTBEATS_KEY = "intel_scan_heartbeats"


async def get_intel_scan_heartbeats(session: AsyncSession) -> dict[str, datetime]:
  result = await session.execute(
    select(PlatformSetting).where(PlatformSetting.key == INTEL_SCAN_HEARTBEATS_KEY)
  )
  row = result.scalar_one_or_none()
  if not row or not row.value:
    return {}
  try:
    payload = json.loads(row.value)
  except json.JSONDecodeError:
    return {}
  heartbeats: dict[str, datetime] = {}
  for source, raw_ts in payload.items():
    if not isinstance(raw_ts, str):
      continue
    try:
      heartbeats[str(source)] = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).replace(
        tzinfo=None
      )
    except ValueError:
      continue
  return heartbeats


async def record_intel_scan_heartbeats(session: AsyncSession, *sources: str) -> None:
  """Record that a source scan completed successfully (caller commits)."""
  if not sources:
    return
  now = datetime.utcnow()
  result = await session.execute(
    select(PlatformSetting).where(PlatformSetting.key == INTEL_SCAN_HEARTBEATS_KEY)
  )
  row = result.scalar_one_or_none()
  heartbeats: dict[str, str] = {}
  if row and row.value:
    try:
      heartbeats = json.loads(row.value)
    except json.JSONDecodeError:
      heartbeats = {}
  for source in sources:
    heartbeats[source] = now.isoformat()
  encoded = json.dumps(heartbeats)
  if row:
    row.value = encoded
    row.updated_at = now
  else:
    session.add(PlatformSetting(key=INTEL_SCAN_HEARTBEATS_KEY, value=encoded))
