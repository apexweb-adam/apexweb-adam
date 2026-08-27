"""Trigger Render redeploy when the running build is behind main."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.database import SessionLocal
from app.engines.deploy_status import build_deploy_status
from app.engines.platform_settings import (
  get_platform_setting,
  get_render_deploy_hook,
  set_platform_setting,
)

LAST_REDEPLOY_KEY = "last_redeploy_trigger_at"
REDEPLOY_COOLDOWN = timedelta(hours=1)


async def resolve_render_deploy_hook() -> str:
  env_hook = os.environ.get("RENDER_DEPLOY_HOOK", "").strip()
  if env_hook:
    return env_hook
  async with SessionLocal() as session:
    stored = await get_render_deploy_hook(session)
    return (stored or "").strip()


async def maybe_trigger_stale_redeploy() -> dict[str, Any]:
  """POST to RENDER_DEPLOY_HOOK once per hour when deploy is stale."""
  hook = await resolve_render_deploy_hook()
  status = await build_deploy_status()

  if not status.get("is_stale"):
    return {"triggered": False, "reason": "deploy_current", "deploy": status}
  if not hook:
    return {"triggered": False, "reason": "no_deploy_hook", "deploy": status}

  async with SessionLocal() as session:
    last_raw = await get_platform_setting(session, LAST_REDEPLOY_KEY)
    if last_raw:
      try:
        last = datetime.fromisoformat(last_raw.replace("Z", "+00:00")).replace(tzinfo=None)
        if datetime.utcnow() - last < REDEPLOY_COOLDOWN:
          return {"triggered": False, "reason": "cooldown", "deploy": status}
      except ValueError:
        pass

  try:
    async with httpx.AsyncClient(timeout=15.0) as client:
      response = await client.post(hook)
      response.raise_for_status()
  except Exception as exc:
    return {"triggered": False, "reason": f"hook_failed: {exc}", "deploy": status}

  async with SessionLocal() as session:
    await set_platform_setting(session, LAST_REDEPLOY_KEY, datetime.utcnow().isoformat())

  return {
    "triggered": True,
    "reason": "stale_redeploy",
    "deploy": status,
    "message": "Render redeploy triggered via deploy hook",
  }
