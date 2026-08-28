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
RENDER_SERVICE_NAME = "apex-trading-backend"


async def resolve_render_deploy_hook() -> str:
  env_hook = os.environ.get("RENDER_DEPLOY_HOOK", "").strip()
  if env_hook:
    return env_hook
  async with SessionLocal() as session:
    stored = await get_render_deploy_hook(session)
    return (stored or "").strip()


async def trigger_render_api_deploy(*, clear_cache: bool = False) -> dict[str, Any]:
  """Create a deploy via Render API — pulls latest commit from connected GitHub repo."""
  api_key = os.environ.get("RENDER_API_KEY", "").strip()
  if not api_key:
    return {"ok": False, "reason": "no_render_api_key"}

  headers = {"Authorization": f"Bearer {api_key}"}
  async with httpx.AsyncClient(timeout=20.0) as client:
    services = await client.get("https://api.render.com/v1/services?limit=100", headers=headers)
    services.raise_for_status()
    service_id = None
    for item in services.json():
      svc = item.get("service") or item
      if svc.get("name") == RENDER_SERVICE_NAME:
        service_id = svc["id"]
        break
    if not service_id:
      return {"ok": False, "reason": "service_not_found"}

    body: dict[str, Any] = {}
    if clear_cache:
      body["clearCache"] = "clear"
    deploy = await client.post(
      f"https://api.render.com/v1/services/{service_id}/deploys",
      headers={**headers, "Content-Type": "application/json"},
      json=body,
    )
    deploy.raise_for_status()
    return {"ok": True, "service_id": service_id, "deploy": deploy.json()}


async def maybe_trigger_stale_redeploy(*, force: bool = False) -> dict[str, Any]:
  """Redeploy once per hour when deploy is stale — prefer Render API over deploy hook."""
  status = await build_deploy_status()

  if not force and not status.get("is_stale"):
    return {"triggered": False, "reason": "deploy_current", "deploy": status}

  if not force:
    async with SessionLocal() as session:
      last_raw = await get_platform_setting(session, LAST_REDEPLOY_KEY)
      if last_raw:
        try:
          last = datetime.fromisoformat(last_raw.replace("Z", "+00:00")).replace(tzinfo=None)
          if datetime.utcnow() - last < REDEPLOY_COOLDOWN:
            return {"triggered": False, "reason": "cooldown", "deploy": status}
        except ValueError:
          pass

  commits_behind = int(status.get("commits_behind") or 0)
  clear_cache = force or commits_behind > 0

  api_result = await trigger_render_api_deploy(clear_cache=clear_cache)
  if api_result.get("ok"):
    async with SessionLocal() as session:
      await set_platform_setting(session, LAST_REDEPLOY_KEY, datetime.utcnow().isoformat())
    return {
      "triggered": True,
      "reason": "force_redeploy_api" if force else "stale_redeploy_api",
      "deploy": status,
      "message": "Render redeploy triggered via Render API",
      "clear_cache": clear_cache,
      "forced": force,
    }

  hook = await resolve_render_deploy_hook()
  if not hook:
    return {
      "triggered": False,
      "reason": api_result.get("reason") or "no_deploy_hook",
      "deploy": status,
    }

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
    "reason": "force_redeploy_hook" if force else "stale_redeploy_hook",
    "deploy": status,
    "message": "Render redeploy triggered via deploy hook",
    "forced": force,
  }
