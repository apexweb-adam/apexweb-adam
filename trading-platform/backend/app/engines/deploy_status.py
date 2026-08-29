"""Compare deployed commit against GitHub main for deploy staleness."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any

import httpx

GITHUB_REPO = os.environ.get("GITHUB_REPO", "apexweb-adam/apexweb-adam")
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"

_deploy_status_cache: dict[str, Any] | None = None
_deploy_status_cached_at: float = 0.0
DEPLOY_STATUS_CACHE_TTL_SECONDS = 60


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
DEFAULT_VERIFIED_DASHBOARD_URL = "https://apex-trading-dashboard-4am3sz5kv-apexweb-adams-projects.vercel.app"
DEFAULT_VERIFIED_DEPLOYMENT_ID = "dpl_GQTTm469KGGRkiKfwrULaLieM5VE"
EXPECTED_DASHBOARD_BUNDLE = "2026-08-29-r45"
EXPECTED_PLATFORM_REVISION = "2026-08-29-r207"
GIT_MAIN_ALIAS = "apex-trading-dashboard-git-main"
ACCEPTABLE_DASHBOARD_BUNDLES = frozenset({
  "2026-08-27-r9", "2026-08-27-r10", "2026-08-27-r11", "2026-08-27-r12",
  "2026-08-27-r13", "2026-08-27-r14", "2026-08-27-r15", "2026-08-27-r16",
  "2026-08-28-r17", "2026-08-28-r18", "2026-08-28-r19", "2026-08-28-r20",
  "2026-08-28-r30", "2026-08-28-r29", "2026-08-28-r28", "2026-08-28-r27", "2026-08-28-r26", "2026-08-28-r25", "2026-08-28-r24", "2026-08-28-r23", "2026-08-28-r22", "2026-08-28-r21",
  "2026-08-29-r31",
  "2026-08-29-r32",
  "2026-08-29-r33",
  "2026-08-29-r34",
  "2026-08-29-r35",
  "2026-08-29-r36",
  "2026-08-29-r37",
  "2026-08-29-r38",
  "2026-08-29-r39",
  "2026-08-29-r40",
  "2026-08-29-r41",
  "2026-08-29-r42",
  "2026-08-29-r43",
  "2026-08-29-r44",
  "2026-08-29-r45",
})


def configured_verified_dashboard_url() -> str:
  return os.environ.get("VERIFIED_DASHBOARD_URL", DEFAULT_VERIFIED_DASHBOARD_URL)


def configured_verified_deployment_id() -> str:
  return os.environ.get("VERIFIED_VERCEL_DEPLOYMENT_ID", DEFAULT_VERIFIED_DEPLOYMENT_ID)


def _platform_root() -> str:
  here = os.path.dirname(os.path.abspath(__file__))
  return os.path.normpath(os.path.join(here, "../../.."))


def configured_public_dashboard_url() -> str | None:
  """Cloud Agent / tunnel CRM URL when set (PUBLIC_DASHBOARD_URL or .platform-urls.json)."""
  env_url = os.environ.get("PUBLIC_DASHBOARD_URL", "").strip()
  if env_url:
    return env_url.rstrip("/")

  paths: list[str] = []
  custom = os.environ.get("PLATFORM_URLS_FILE", "").strip()
  if custom:
    paths.append(custom)
  platform_root = _platform_root()
  paths.append(os.path.join(platform_root, ".platform-urls.json"))
  dash_file = os.path.join(platform_root, ".dashboard-tunnel-url")
  if os.path.isfile(dash_file):
    try:
      with open(dash_file, encoding="utf-8") as handle:
        url = handle.read().strip().rstrip("/")
      if url.startswith("http"):
        return url
    except Exception:
      pass
  for path in paths:
    try:
      if not os.path.isfile(path):
        continue
      import json
      with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
      url = (data.get("dashboard_url") or "").strip().rstrip("/")
      if url:
        return url
    except Exception:
      continue
  return None


def configured_public_backend_url() -> str | None:
  env_url = os.environ.get("PUBLIC_BACKEND_URL", "").strip()
  if env_url:
    return env_url.rstrip("/")

  paths: list[str] = []
  custom = os.environ.get("PLATFORM_URLS_FILE", "").strip()
  if custom:
    paths.append(custom)
  platform_root = _platform_root()
  paths.append(os.path.join(platform_root, ".platform-urls.json"))
  tunnel_file = os.path.join(platform_root, ".tunnel-url")
  if os.path.isfile(tunnel_file):
    try:
      with open(tunnel_file, encoding="utf-8") as handle:
        url = handle.read().strip().rstrip("/")
      if url.startswith("http"):
        return url
    except Exception:
      pass
  for path in paths:
    try:
      if not os.path.isfile(path):
        continue
      import json
      with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
      url = (data.get("backend_url") or "").strip().rstrip("/")
      if url:
        return url
    except Exception:
      continue
  return None


def is_git_main_alias(url: str) -> bool:
  return GIT_MAIN_ALIAS in (url or "")


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

  # Configured verified URL first — env is authoritative when probe succeeds.
  add(configured_verified_dashboard_url())
  # Newest main-branch previews (r31 recovery preview) — prefer before stale git-main alias.
  add("https://apex-trading-dashboard-4am3sz5kv-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-fh95xdpz2-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-73nruanbo-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-r8ur3gw5s-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-gdjavkmox-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-aiuir3aha-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-ihyxoyq1e-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-dt4ezyvny-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-2sngnu6ma-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-39gtc4hgx-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-mz9mzjoaq-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-jwi0so16v-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-edv5hefqa-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-4dc50ssd9-apexweb-adams-projects.vercel.app")
  add("https://apex-trading-dashboard-ekn183k28-apexweb-adams-projects.vercel.app")
  for part in (os.environ.get("VERIFIED_DASHBOARD_FALLBACKS") or "").split(","):
    add(part)
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
    return 100
  if "-r" in revision:
    try:
      return int(revision.rsplit("-r", 1)[-1])
    except ValueError:
      pass
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


async def probe_configured_verified_dashboard() -> dict[str, Any] | None:
  """Probe VERIFIED_DASHBOARD_URL directly before broader discovery."""
  url = configured_verified_dashboard_url()
  cfg = await probe_dashboard_config(url)
  if not cfg or not bundle_is_acceptable(cfg):
    return None
  return {
    "verified_dashboard_url": url,
    "vercel_bundle_revision": cfg.get("bundleRevision"),
    "discovered": False,
    "_rank": bundle_rank(cfg),
  }


async def discover_verified_dashboard() -> dict[str, Any]:
  """Probe candidates and return the URL with the best acceptable bundle."""
  configured_probe = await probe_configured_verified_dashboard()
  configured_url = configured_verified_dashboard_url()
  configured_rank = (configured_probe or {}).get("_rank", -1)

  best: dict[str, Any] | None = configured_probe
  best_rank = configured_rank

  for url in verified_dashboard_candidates():
    if url == configured_url and configured_probe:
      continue
    cfg = await probe_dashboard_config(url)
    if not cfg or not bundle_is_acceptable(cfg):
      continue
    rank = bundle_rank(cfg)
    # Never let stale git-main beat a working configured preview.
    if is_git_main_alias(url) and configured_rank > rank:
      continue
    if rank > best_rank:
      best_rank = rank
      best = {
        "verified_dashboard_url": url,
        "vercel_bundle_revision": cfg.get("bundleRevision"),
        "discovered": url != configured_url,
        "_rank": rank,
      }

  if best:
    best.pop("_rank", None)
    return best

  fallback = configured_url
  return {
    "verified_dashboard_url": fallback,
    "vercel_bundle_revision": None,
    "discovered": False,
  }


def deployed_git_commit() -> str | None:
  from app.config import settings

  return settings.render_git_commit or os.environ.get("RENDER_GIT_COMMIT") or None


async def fetch_latest_main_commit() -> dict[str, Any] | None:
  """Resolve main HEAD — ref endpoint first (lighter, survives rate limits)."""
  ref = await fetch_main_sha_via_ref()
  if ref and ref.get("sha"):
    headers = github_headers()
    for attempt in range(2):
      try:
        async with httpx.AsyncClient(timeout=10.0) as client:
          response = await client.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/commits/{ref['sha']}",
            headers=headers,
          )
          if response.status_code == 200:
            data = response.json()
            commit = data.get("commit") or {}
            return {
              "sha": data.get("sha") or ref["sha"],
              "message": (commit.get("message") or "").split("\n")[0],
              "committed_at": (commit.get("author") or {}).get("date"),
            }
          if response.status_code == 403 and attempt < 1:
            import asyncio
            await asyncio.sleep(1.5)
            continue
      except Exception:
        if attempt < 1:
          import asyncio
          await asyncio.sleep(1.0)
          continue
    return ref

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
  return await fetch_main_sha_via_ref()


async def fetch_main_sha_via_ref() -> dict[str, Any] | None:
  """Lightweight fallback when commits/main is rate-limited."""
  headers = github_headers()
  try:
    async with httpx.AsyncClient(timeout=10.0) as client:
      response = await client.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/git/ref/heads/main",
        headers=headers,
      )
      if response.status_code == 200:
        sha = (response.json().get("object") or {}).get("sha")
        if sha:
          return {"sha": sha, "message": "", "committed_at": None}
  except Exception:
    pass
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


async def fetch_github_commit_statuses(sha: str) -> list[dict[str, str]]:
  """Legacy commit statuses for a SHA (includes third-party GitHub App integrations)."""
  if not sha:
    return []
  headers = github_headers()
  try:
    async with httpx.AsyncClient(timeout=10.0) as client:
      response = await client.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/commits/{sha}/statuses",
        headers=headers,
      )
      if response.status_code != 200:
        return []
      rows = response.json()
      return [
        {
          "context": (row.get("context") or "").strip(),
          "state": (row.get("state") or "").strip().lower(),
          "description": (row.get("description") or "").strip(),
        }
        for row in rows
        if isinstance(row, dict)
      ]
  except Exception:
    return []


async def fetch_github_check_suites(sha: str) -> list[dict[str, str]]:
  """Check suites from GitHub Apps (Vercel, Netlify, etc.) — primary checksPass signal."""
  if not sha:
    return []
  headers = github_headers()
  try:
    async with httpx.AsyncClient(timeout=10.0) as client:
      response = await client.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/commits/{sha}/check-suites",
        headers=headers,
        params={"per_page": 100},
      )
      if response.status_code != 200:
        return []
      rows = response.json()
      suites = rows.get("check_suites") if isinstance(rows, dict) else rows
      if not isinstance(suites, list):
        return []
      out: list[dict[str, str]] = []
      for suite in suites:
        if not isinstance(suite, dict):
          continue
        context = ((suite.get("app") or {}).get("name") or "").strip()
        status = (suite.get("status") or "").strip().lower()
        conclusion = (suite.get("conclusion") or "").strip().lower()
        if not context:
          continue
        if status == "completed":
          state = conclusion or "success"
        else:
          state = status
        out.append({"context": context, "state": state, "description": ""})
      return out
  except Exception:
    return []


async def fetch_github_checks(sha: str) -> list[dict[str, str]]:
  """Merge legacy statuses and check suites for Render checksPass analysis."""
  statuses = await fetch_github_commit_statuses(sha)
  suites = await fetch_github_check_suites(sha)
  return statuses + suites


def summarize_github_checks_blocker(statuses: list[dict[str, str]]) -> dict[str, Any]:
  """Detect third-party checks that keep combined commit state pending (blocks Render checksPass)."""
  if not statuses:
    return {"blocked": False, "combined_state": "unknown", "blocking_contexts": []}

  rank = {"success": 4, "skipped": 4, "neutral": 4, "failure": 3, "error": 3, "cancelled": 3, "pending": 2, "queued": 1, "in_progress": 2}
  by_context: dict[str, str] = {}
  for row in statuses:
    context = row.get("context") or ""
    state = row.get("state") or ""
    if not context or not state:
      continue
    prev = by_context.get(context)
    if prev is None or rank.get(state, 0) > rank.get(prev, 0):
      by_context[context] = state

  blocking: list[str] = []
  for context, state in sorted(by_context.items()):
    if context == "GitHub Actions":
      continue
    if state not in ("success", "skipped", "neutral"):
      blocking.append(f"{context} ({state})")

  combined = "success"
  if any(s in ("queued", "pending", "in_progress") for s in by_context.values()):
    combined = "pending"
  elif any(s in ("failure", "error", "cancelled") for s in by_context.values()):
    combined = "failure"
  elif blocking:
    combined = "pending"

  return {
    "blocked": bool(blocking),
    "combined_state": combined,
    "blocking_contexts": blocking,
  }


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
  global _deploy_status_cache, _deploy_status_cached_at
  now = time.monotonic()
  if _deploy_status_cache is not None and (now - _deploy_status_cached_at) < DEPLOY_STATUS_CACHE_TTL_SECONDS:
    return _deploy_status_cache

  result = await _build_deploy_status_uncached()
  _deploy_status_cache = result
  _deploy_status_cached_at = now
  return result


async def _build_deploy_status_uncached() -> dict[str, Any]:
  deployed = deployed_git_commit()
  latest = await fetch_latest_main_commit()
  latest_sha = (latest or {}).get("sha")

  if deployed and not latest_sha:
    ref = await fetch_main_sha_via_ref()
    if ref and ref.get("sha"):
      latest_sha = ref["sha"]
      latest = latest or ref

  compare = await fetch_compare_to_main(deployed) if deployed else None
  if deployed and not compare and latest_sha and deployed != latest_sha:
    compare = await fetch_compare_to_main(deployed)

  is_stale = False
  pending_changes: list[dict[str, str]] = []
  github_verified = False

  if compare is not None:
    github_verified = True
    if (compare.get("ahead_by") or 0) > 0:
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
  elif deployed and latest_sha:
    github_verified = True
    if deployed != latest_sha:
      is_stale = True
      pending_changes = (compare or {}).get("commits") or []

  if not github_verified and deployed:
    ref = await fetch_main_sha_via_ref()
    if ref and ref.get("sha"):
      github_verified = True
      latest_sha = ref["sha"]
      if not latest:
        latest = ref
      if deployed != latest_sha:
        is_stale = True

  if is_stale and deployed and not pending_changes:
    pending_changes = await fetch_commits_since(deployed)

  if deployed and not github_verified:
    is_stale = True
    next_steps_unknown = (
      "GitHub API unavailable — cannot confirm deploy freshness. "
      "Set GITHUB_TOKEN on Render or verify manually in Render dashboard."
    )
  else:
    next_steps_unknown = None

  stale_minutes: int | None = None
  committed_at = (latest or {}).get("committed_at")
  if is_stale and committed_at:
    try:
      committed = datetime.fromisoformat(committed_at.replace("Z", "+00:00"))
      stale_minutes = max(0, int((datetime.now(committed.tzinfo) - committed).total_seconds() // 60))
    except Exception:
      stale_minutes = None

  next_steps: list[str] = []
  if next_steps_unknown:
    next_steps.append(next_steps_unknown)
  if is_stale and not next_steps_unknown:
    next_steps.append(
      f"Render deploy is stale — running {deployed[:12] if deployed else '?'} "
      f"but main is {latest_sha[:12] if latest_sha else '?'}. "
      "Do NOT use Deploy Hook when behind main (it redeploys the old commit). "
      "Use Render Manual Deploy → latest commit, or set RENDER_API_KEY in GitHub secrets. "
      "If Auto-Deploy is 'After CI Checks Pass', switch to 'On Commit' — Vercel failures block checksPass."
    )
    if pending_changes:
      summaries = [c["message"] for c in pending_changes[:3]]
      next_steps.append(f"Pending on main ({len(pending_changes)} commits): {'; '.join(summaries)}")

  github_checks: dict[str, Any] = {"blocked": False, "combined_state": "unknown", "blocking_contexts": []}
  if latest_sha:
    check_rows = await fetch_github_checks(latest_sha)
    github_checks = summarize_github_checks_blocker(check_rows)
    if github_checks.get("blocked"):
      blockers = ", ".join(github_checks.get("blocking_contexts") or [])
      next_steps.append(
        "GitHub commit status blocked for Render checksPass — "
        f"queued/pending integrations: {blockers}. "
        "Disable unused repo integrations (Vercel/Netlify/Supabase/Cursor/Claude GitHub Apps) "
        "under GitHub → Settings → Integrations, or set Render Auto-Deploy to On Commit."
      )

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

  platform_revision = os.environ.get("PLATFORM_REVISION", "").strip() or None

  public_dashboard = configured_public_dashboard_url()
  public_backend = configured_public_backend_url()
  if public_dashboard:
    vercel["public_dashboard_url"] = public_dashboard
  if public_backend:
    vercel["public_backend_url"] = public_backend

  return {
    "git_commit": deployed,
    "git_branch": os.environ.get("RENDER_GIT_BRANCH"),
    "platform_revision": platform_revision,
    "expected_platform_revision": EXPECTED_PLATFORM_REVISION,
    "platform_revision_current": platform_revision == EXPECTED_PLATFORM_REVISION if platform_revision else None,
    "latest_main_commit": latest_sha,
    "latest_main_message": (latest or {}).get("message"),
    "is_stale": is_stale,
    "stale_minutes": stale_minutes,
    "pending_changes": pending_changes,
    "commits_behind": len(pending_changes) if pending_changes else (1 if is_stale and not github_verified else 0),
    "github_verified": github_verified,
    "github_checks_blocker": github_checks,
    "next_steps": next_steps,
    **vercel,
  }


async def recommended_dashboard_url() -> str:
  """Return the best live CRM URL — public tunnel, then verified preview, then production."""
  public = configured_public_dashboard_url()
  if public:
    cfg = await probe_dashboard_config(public)
    if cfg and bundle_is_acceptable(cfg):
      return public

  configured_probe = await probe_configured_verified_dashboard()
  if configured_probe:
    return configured_probe["verified_dashboard_url"]

  deploy = await build_deploy_status()
  verified = deploy.get("verified_dashboard_url") or configured_verified_dashboard_url()
  verified_bundle = deploy.get("verified_bundle_revision")
  if verified_bundle and bundle_rank({"bundleRevision": verified_bundle, "features": {"activeGate": True}}) < bundle_rank(
    {"bundleRevision": EXPECTED_DASHBOARD_BUNDLE, "features": {"activeGate": True}}
  ):
    if is_git_main_alias(verified):
      return configured_verified_dashboard_url()
  if deploy.get("vercel_bundle_stale"):
    return verified
  return (
    deploy.get("dashboard_url")
    or verified
    or configured_verified_dashboard_url()
  )
