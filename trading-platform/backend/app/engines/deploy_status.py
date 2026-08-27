"""Compare deployed commit against GitHub main for deploy staleness."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

GITHUB_REPO = os.environ.get("GITHUB_REPO", "apexweb-adam/apexweb-adam")
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"


def deployed_git_commit() -> str | None:
  from app.config import settings

  return settings.render_git_commit or os.environ.get("RENDER_GIT_COMMIT") or None


async def fetch_latest_main_commit() -> dict[str, Any] | None:
  try:
    async with httpx.AsyncClient(timeout=8.0) as client:
      response = await client.get(
        GITHUB_API,
        headers={"Accept": "application/vnd.github+json"},
      )
      if response.status_code != 200:
        return None
      data = response.json()
      commit = data.get("commit") or {}
      return {
        "sha": data.get("sha"),
        "message": (commit.get("message") or "").split("\n")[0],
        "committed_at": (commit.get("author") or {}).get("date"),
      }
  except Exception:
    return None


async def build_deploy_status() -> dict[str, Any]:
  deployed = deployed_git_commit()
  latest = await fetch_latest_main_commit()
  latest_sha = (latest or {}).get("sha")
  is_stale = bool(deployed and latest_sha and deployed != latest_sha)

  stale_minutes: int | None = None
  committed_at = (latest or {}).get("committed_at")
  if is_stale and committed_at:
    try:
      committed = datetime.fromisoformat(committed_at.replace("Z", "+00:00"))
      stale_minutes = max(0, int((datetime.now(committed.tzinfo) - committed).total_seconds() // 60))
    except Exception:
      stale_minutes = None

  next_steps: list[str] = []
  if is_stale:
    next_steps.append(
      f"Render deploy is stale — running {deployed[:12] if deployed else '?'} "
      f"but main is {latest_sha[:12] if latest_sha else '?'}. "
      "Trigger manual deploy in Render dashboard or set RENDER_DEPLOY_HOOK in GitHub secrets."
    )

  return {
    "git_commit": deployed,
    "git_branch": os.environ.get("RENDER_GIT_BRANCH"),
    "latest_main_commit": latest_sha,
    "latest_main_message": (latest or {}).get("message"),
    "is_stale": is_stale,
    "stale_minutes": stale_minutes,
    "next_steps": next_steps,
  }
