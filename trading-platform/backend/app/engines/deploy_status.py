"""Compare deployed commit against GitHub main for deploy staleness."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

GITHUB_REPO = os.environ.get("GITHUB_REPO", "apexweb-adam/apexweb-adam")
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"


def github_headers() -> dict[str, str]:
  headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "ApexTradingPlatform/1.0",
  }
  token = os.environ.get("GITHUB_TOKEN", "").strip()
  if token:
    headers["Authorization"] = f"Bearer {token}"
  return headers
PRODUCTION_DASHBOARD_URL = "https://apex-trading-dashboard-flame.vercel.app"
DEFAULT_VERIFIED_DASHBOARD_URL = (
  "https://apex-trading-dashboard-4dc50ssd9-apexweb-adams-projects.vercel.app"
)
DEFAULT_VERIFIED_DEPLOYMENT_ID = "dpl_G9TugiNNhpv4JZubTmy6ijmpbbkU"
EXPECTED_DASHBOARD_BUNDLE = "2026-08-27-r12"
ACCEPTABLE_DASHBOARD_BUNDLES = frozenset({"2026-08-27-r9", "2026-08-27-r10", "2026-08-27-r11", "2026-08-27-r12"})


def configured_verified_dashboard_url() -> str:
  return os.environ.get("VERIFIED_DASHBOARD_URL", DEFAULT_VERIFIED_DASHBOARD_URL)


def configured_verified_deployment_id() -> str:
  return os.environ.get("VERIFIED_VERCEL_DEPLOYMENT_ID", DEFAULT_VERIFIED_DEPLOYMENT_ID)


def verified_dashboard_candidates() -> list[str]:
  """Ordered dashboard URLs to probe when production bundle is stale."""
  candidates: list[str] = []
  seen: set[str] = set()

  def add(url: str | None) -> None:
    if not url:
      return
    normalized = url.strip().rstrip("/")
    if normalized and normalized not in seen:
      seen.add(normalized)
      candidates.append(normalized)

  # Probe best-known previews first so stale Render env vars do not block r10/r11 discovery.
  add(DEFAULT_VERIFIED_DASHBOARD_URL)
  add("https://apex-trading-dashboard-ekn183k28-apexweb-adams-projects.vercel.app")
  add(configured_verified_dashboard_url())
  for part in (os.environ.get("VERIFIED_DASHBOARD_FALLBACKS") or "").split(","):
    add(part)
  add("https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-apexweb-adams-projects.vercel.app")
  return candidates


def bundle_is_current(cfg: dict[str, Any]) -> bool:
  revision = cfg.get("bundleRevision")
  active_gate = (cfg.get("features") or {}).get("activeGate") is True
  return revision == EXPECTED_DASHBOARD_BUNDLE and active_gate


def bundle_is_acceptable(cfg: dict[str, Any]) -> bool:
  revision = cfg.get("bundleRevision")
  active_gate = (cfg.get("features") or {}).get("activeGate") is True
  return revision in ACCEPTABLE_DASHBOARD_BUNDLES and active_gate


def bundle_rank(cfg: dict[str, Any]) -> int:
  revision = str(cfg.get("bundleRevision") or "")
  if revision == EXPECTED_DASHBOARD_BUNDLE:
    return 4
  if revision == "2026-08-27-r11":
    return 3
  if revision == "2026-08-27-r10":
    return 2
  if revision in ACCEPTABLE_DASHBOARD_BUNDLES:
    return 1
  return 0


async def probe_dashboard_config(url: str) -> dict[str, Any] | None:
  try:
    async with httpx.AsyncClient(timeout=8.0) as client:
      response = await client.get(f"{url}/api/config")
      if response.status_code != 200:
        return None
      cfg = response.json()
      return cfg if isinstance(cfg, dict) else None
  except Exception:
    return None


async def discover_verified_dashboard() -> dict[str, Any]:
  """Probe candidates and return the URL with the best acceptable bundle."""
  best: dict[str, Any] | None = None
  best_rank = -1

  for url in verified_dashboard_candidates():
    cfg = await probe_dashboard_config(url)
    if not cfg or not bundle_is_acceptable(cfg):
      continue
    rank = bundle_rank(cfg)
    if rank > best_rank:
      best_rank = rank
      best = {
        "verified_dashboard_url": url,
        "vercel_bundle_revision": cfg.get("bundleRevision"),
        "discovered": url != configured_verified_dashboard_url(),
      }

  if best:
    return best

  fallback = configured_verified_dashboard_url()
  return {
    "verified_dashboard_url": fallback,
    "vercel_bundle_revision": None,
    "discovered": False,
  }


def deployed_git_commit() -> str | None:
  from app.config import settings

  return settings.render_git_commit or os.environ.get("RENDER_GIT_COMMIT") or None


async def fetch_latest_main_commit() -> dict[str, Any] | None:
  headers = github_headers()
  for attempt in range(3):
    try:
      async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(GITHUB_API, headers=headers)
        if response.status_code == 200:
          data = response.json()
          commit = data.get("commit") or {}
          return {
            "sha": data.get("sha"),
            "message": (commit.get("message") or "").split("\n")[0],
            "committed_at": (commit.get("author") or {}).get("date"),
          }
        if response.status_code == 403 and attempt < 2:
          import asyncio
          await asyncio.sleep(1.5 * (attempt + 1))
          continue
    except Exception:
      if attempt < 2:
        import asyncio
        await asyncio.sleep(1.0)
        continue
  return None


async def fetch_compare_to_main(deployed_sha: str) -> dict[str, Any] | None:
  """Compare deployed SHA to main; primary staleness signal when commits API is rate-limited."""
  if not deployed_sha:
    return None
  headers = github_headers()
  for attempt in range(3):
    try:
      async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
          f"https://api.github.com/repos/{GITHUB_REPO}/compare/{deployed_sha}...main",
          headers=headers,
        )
        if response.status_code == 200:
          data = response.json()
          commits = data.get("commits") or []
          head_sha = commits[-1].get("sha") if commits else data.get("merge_base_commit", {}).get("sha")
          return {
            "ahead_by": data.get("ahead_by", 0),
            "status": data.get("status"),
            "head_sha": head_sha,
            "commits": [
              {
                "sha": (c.get("sha") or "")[:12],
                "message": (c.get("commit") or {}).get("message", "").split("\n")[0],
              }
              for c in commits
            ],
          }
        if response.status_code == 403 and attempt < 2:
          import asyncio
          await asyncio.sleep(1.5 * (attempt + 1))
          continue
    except Exception:
      if attempt < 2:
        import asyncio
        await asyncio.sleep(1.0)
        continue
  return None


async def fetch_commits_since(deployed_sha: str) -> list[dict[str, str]]:
  """List commits on main that are not in the deployed build."""
  compare = await fetch_compare_to_main(deployed_sha)
  return (compare or {}).get("commits") or []


async def probe_production_proxy_operational() -> bool:
  """True when production Vercel serves active-gate via /api/backend proxy."""
  try:
    async with httpx.AsyncClient(timeout=8.0) as client:
      response = await client.get(f"{PRODUCTION_DASHBOARD_URL}/api/backend/active-gate")
      if response.status_code != 200:
        return False
      data = response.json()
      return bool(data.get("active_bots"))
  except Exception:
    return False


async def fetch_vercel_dashboard_bundle() -> dict[str, Any]:
  """Probe production /api/config for dashboard bundle freshness."""
  promote_id = configured_verified_deployment_id()
  promote_url = (
    "https://vercel.com/apexweb-adams-projects/apex-trading-dashboard/deployments"
  )

  try:
    prod_cfg = await probe_dashboard_config(PRODUCTION_DASHBOARD_URL)
    proxy_ok = await probe_production_proxy_operational()
    if prod_cfg and bundle_is_current(prod_cfg):
      return {
        "vercel_bundle_stale": False,
        "vercel_bundle_revision": prod_cfg.get("bundleRevision"),
        "production_proxy_operational": proxy_ok,
        "dashboard_url": PRODUCTION_DASHBOARD_URL,
      }

    discovered = await discover_verified_dashboard()
    verified_url = discovered["verified_dashboard_url"]
    dashboard_url = PRODUCTION_DASHBOARD_URL if proxy_ok else verified_url
    return {
      "vercel_bundle_stale": True,
      "vercel_bundle_revision": (prod_cfg or {}).get("bundleRevision"),
      "production_proxy_operational": proxy_ok,
      "verified_dashboard_url": verified_url,
      "verified_dashboard_discovered": discovered.get("discovered", False),
      "verified_bundle_revision": discovered.get("vercel_bundle_revision"),
      "vercel_promote_deployment_id": promote_id,
      "vercel_promote_url": promote_url,
      "dashboard_url": dashboard_url,
    }
  except Exception:
    verified_url = configured_verified_dashboard_url()
    proxy_ok = await probe_production_proxy_operational()
    return {
      "vercel_bundle_stale": True,
      "production_proxy_operational": proxy_ok,
      "verified_dashboard_url": verified_url,
      "vercel_promote_deployment_id": promote_id,
      "vercel_promote_url": promote_url,
      "dashboard_url": PRODUCTION_DASHBOARD_URL if proxy_ok else verified_url,
    }


async def build_deploy_status() -> dict[str, Any]:
  deployed = deployed_git_commit()
  compare = await fetch_compare_to_main(deployed) if deployed else None
  latest = await fetch_latest_main_commit()
  latest_sha = (latest or {}).get("sha")

  is_stale = False
  pending_changes: list[dict[str, str]] = []
  if deployed and compare and (compare.get("ahead_by") or 0) > 0:
    is_stale = True
    pending_changes = compare.get("commits") or []
    if compare.get("head_sha"):
      latest_sha = compare["head_sha"]
      if not latest:
        latest = {
          "sha": latest_sha,
          "message": (pending_changes[-1].get("message") if pending_changes else ""),
          "committed_at": None,
        }
  elif deployed and latest_sha and deployed != latest_sha:
    is_stale = True
    pending_changes = (compare or {}).get("commits") or []

  if is_stale and deployed and not pending_changes:
    pending_changes = await fetch_commits_since(deployed)

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
    verified = vercel.get("verified_dashboard_url", configured_verified_dashboard_url())
    promote_id = vercel.get("vercel_promote_deployment_id") or configured_verified_deployment_id()
    if vercel.get("production_proxy_operational"):
      next_steps.append(
        "Vercel production bundle is stale but CRM proxy is operational on "
        f"{PRODUCTION_DASHBOARD_URL} — promote {promote_id} for native routes and newest UI, "
        f"or use verified preview: {verified}"
      )
    else:
      next_steps.append(
        "Vercel production dashboard bundle is stale — promote "
        f"{promote_id} in Vercel, "
        f"or use verified preview: {verified}"
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
  verified = deploy.get("verified_dashboard_url") or configured_verified_dashboard_url()
  if deploy.get("vercel_bundle_stale") and verified:
    return verified
  return (
    deploy.get("dashboard_url")
    or verified
    or configured_verified_dashboard_url()
  )
