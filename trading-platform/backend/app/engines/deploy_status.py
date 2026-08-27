"""Compare deployed commit against GitHub main for deploy staleness."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

GITHUB_REPO = os.environ.get("GITHUB_REPO", "apexweb-adam/apexweb-adam")
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
PRODUCTION_DASHBOARD_URL = "https://apex-trading-dashboard-flame.vercel.app"
VERIFIED_DASHBOARD_URL = os.environ.get(
  "VERIFIED_DASHBOARD_URL",
  "https://apex-trading-dashboard-fvmoq5oyj-apexweb-adams-projects.vercel.app",
)
VERIFIED_DEPLOYMENT_ID = os.environ.get(
  "VERIFIED_VERCEL_DEPLOYMENT_ID",
  "dpl_8xcr2CHLWNyDHpHo5cSLsZn3YaU5",
)
EXPECTED_DASHBOARD_BUNDLE = "2026-08-27-r7"


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


async def fetch_commits_since(deployed_sha: str) -> list[dict[str, str]]:
  """List commits on main that are not in the deployed build."""
  if not deployed_sha:
    return []
  try:
    async with httpx.AsyncClient(timeout=8.0) as client:
      response = await client.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/compare/{deployed_sha}...main",
        headers={"Accept": "application/vnd.github+json"},
      )
      if response.status_code != 200:
        return []
      data = response.json()
      return [
        {
          "sha": (c.get("sha") or "")[:12],
          "message": (c.get("commit") or {}).get("message", "").split("\n")[0],
        }
        for c in data.get("commits") or []
      ]
  except Exception:
    return []


async def fetch_vercel_dashboard_bundle() -> dict[str, Any]:
  """Probe production /api/config for dashboard bundle freshness."""
  try:
    async with httpx.AsyncClient(timeout=8.0) as client:
      response = await client.get(f"{PRODUCTION_DASHBOARD_URL}/api/config")
      if response.status_code != 200:
        return {"vercel_bundle_stale": True, "vercel_bundle_revision": None}
      cfg = response.json()
      revision = cfg.get("bundleRevision")
      active_gate = (cfg.get("features") or {}).get("activeGate") is True
      current = revision == EXPECTED_DASHBOARD_BUNDLE and active_gate
      out: dict[str, Any] = {
        "vercel_bundle_stale": not current,
        "vercel_bundle_revision": revision,
        "dashboard_url": PRODUCTION_DASHBOARD_URL if current else VERIFIED_DASHBOARD_URL,
      }
      if not current:
        out["verified_dashboard_url"] = VERIFIED_DASHBOARD_URL
        out["vercel_promote_deployment_id"] = VERIFIED_DEPLOYMENT_ID
        out["vercel_promote_url"] = (
          "https://vercel.com/apexweb-adams-projects/apex-trading-dashboard/deployments"
        )
      return out
  except Exception:
    return {
      "vercel_bundle_stale": True,
      "verified_dashboard_url": VERIFIED_DASHBOARD_URL,
      "vercel_promote_deployment_id": VERIFIED_DEPLOYMENT_ID,
      "dashboard_url": VERIFIED_DASHBOARD_URL,
    }


async def build_deploy_status() -> dict[str, Any]:
  deployed = deployed_git_commit()
  latest = await fetch_latest_main_commit()
  latest_sha = (latest or {}).get("sha")
  is_stale = bool(deployed and latest_sha and deployed != latest_sha)
  pending_changes = await fetch_commits_since(deployed) if is_stale and deployed else []

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
    if pending_changes:
      summaries = [c["message"] for c in pending_changes[:3]]
      next_steps.append(f"Pending on main ({len(pending_changes)} commits): {'; '.join(summaries)}")

  vercel = await fetch_vercel_dashboard_bundle()
  if vercel.get("vercel_bundle_stale"):
    next_steps.append(
      "Vercel production dashboard bundle is stale — promote "
      f"{vercel.get('vercel_promote_deployment_id', VERIFIED_DEPLOYMENT_ID)} in Vercel, "
      f"or use verified preview: {vercel.get('verified_dashboard_url', VERIFIED_DASHBOARD_URL)}"
    )

  return {
    "git_commit": deployed,
    "git_branch": os.environ.get("RENDER_GIT_BRANCH"),
    "latest_main_commit": latest_sha,
    "latest_main_message": (latest or {}).get("message"),
    "is_stale": is_stale,
    "stale_minutes": stale_minutes,
    "pending_changes": pending_changes,
    "commits_behind": len(pending_changes),
    "next_steps": next_steps,
    **vercel,
  }


async def recommended_dashboard_url() -> str:
  deploy = await build_deploy_status()
  return (
    deploy.get("dashboard_url")
    or deploy.get("verified_dashboard_url")
    or VERIFIED_DASHBOARD_URL
  )
