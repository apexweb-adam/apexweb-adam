"""Compare deployed commit against GitHub main for deploy staleness."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

GITHUB_REPO = os.environ.get("GITHUB_REPO", "apexweb-adam/apexweb-adam")
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"

_deploy_status_cache: dict[str, Any] | None = None
_deploy_status_cached_at: float = 0.0
_discover_verified_cache: dict[str, Any] | None = None
_discover_verified_cached_at: float = 0.0
DISCOVER_VERIFIED_CACHE_TTL_SECONDS = 120
DEPLOY_STATUS_CACHE_TTL_SECONDS = 60
CME_DEPLOY_REMINDER_MINUTES = 360
CME_DEPLOY_WINDOW_START_MINUTES = 360
CME_DEPLOY_WINDOW_END_MINUTES = 240
DEPLOY_COMMAND = "TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh"
WAIT_FOR_DEPLOY_COMMAND = "bash trading-platform/scripts/wait-for-render-deploy.sh --verify"
RUN_DEPLOY_WINDOW_COMMAND = "bash trading-platform/scripts/run-deploy-window.sh"


def build_cme_deploy_window(
  *,
  platform_revision_current: bool | None,
  cme_minutes_until_open: int | None,
  cme_in_session: bool = False,
) -> dict[str, Any] | None:
  """Countdown to the ideal Render deploy window (4–6h before CME reopen)."""
  if platform_revision_current is not False:
    return None
  if cme_in_session or cme_minutes_until_open is None:
    return None

  mins = int(cme_minutes_until_open)
  in_window = CME_DEPLOY_WINDOW_END_MINUTES <= mins <= CME_DEPLOY_WINDOW_START_MINUTES
  until_opens = max(0, mins - CME_DEPLOY_WINDOW_START_MINUTES)
  until_closes = max(0, mins - CME_DEPLOY_WINDOW_END_MINUTES)
  now = datetime.utcnow()
  window_opens_at = (now + timedelta(minutes=until_opens)).isoformat() if until_opens else None
  window_closes_at = (now + timedelta(minutes=until_closes)).isoformat()

  if in_window:
    hours, rem = divmod(mins, 60)
    message = (
      f"Deploy window active — CME reopen in {hours}h {rem}m "
      f"(deploy before {window_closes_at[:16].replace('T', ' ')} UTC)"
    )
  elif mins > CME_DEPLOY_WINDOW_START_MINUTES:
    hours, rem = divmod(until_opens, 60)
    message = (
      f"Deploy window opens in {hours}h {rem}m "
      f"({window_opens_at[:16].replace('T', ' ')} UTC)"
    )
  else:
    hours, rem = divmod(mins, 60)
    message = (
      f"CME reopen in {hours}h {rem}m — deploy window closed, "
      "risky to rotate this close to open"
    )

  return {
    "in_window": in_window,
    "window_closed": mins < CME_DEPLOY_WINDOW_END_MINUTES,
    "minutes_until_open": mins,
    "minutes_until_window_opens": until_opens,
    "minutes_until_window_closes": until_closes if in_window else None,
    "window_opens_at_utc": window_opens_at,
    "window_closes_at_utc": window_closes_at,
    "message": message,
    "deploy_command": DEPLOY_COMMAND,
    "verify_command": "bash trading-platform/scripts/verify-pre-deploy.sh",
    "wait_for_deploy_command": WAIT_FOR_DEPLOY_COMMAND,
    "run_deploy_window_command": RUN_DEPLOY_WINDOW_COMMAND,
    "weekend_ops_command": WEEKEND_OPS_VERIFY_COMMAND,
  }


DASHBOARD_BUNDLE_VERIFY_COMMAND = "bash trading-platform/scripts/verify-dashboard-bundle.sh"
WEEKEND_OPS_VERIFY_COMMAND = "bash trading-platform/scripts/verify-weekend-ops.sh"


def format_dashboard_bundle_crm_html(
  *,
  prod_bundle: str,
  expected_bundle: str,
  promote_id: str | None = None,
  verify_command: str = DASHBOARD_BUNDLE_VERIFY_COMMAND,
) -> str:
  """Render Vercel bundle lag warning for the /crm landing page."""
  promote_line = ""
  if promote_id:
    promote_line = (
      f"<p class='muted' style='margin-top:0;font-family:monospace;font-size:0.8rem;'>"
      f"Promote: <code>bash trading-platform/scripts/promote-vercel-dashboard.sh {promote_id}</code></p>"
    )
  return f"""<div class="card" style="border-color:#4c1d95;background:#1a1033;">
    <h2 style="color:#c4b5fd;">Dashboard bundle behind code</h2>
    <p class="muted" style="margin-top:0;">Production Vercel reports <strong>{prod_bundle}</strong> but code expects <strong>{expected_bundle}</strong>. CRM proxy on -flame remains operational; promote or wait for Vercel build quota.</p>
    <p class="muted" style="margin-top:0;font-family:monospace;font-size:0.8rem;">{verify_command}</p>
    {promote_line}
  </div>"""


def format_cme_deploy_window_crm_html(window: dict[str, Any]) -> str:
  """Render deploy window countdown for the /crm landing page."""
  if window.get("window_closed"):
    title = "Deploy window closed"
    color = "#f87171"
  elif window.get("in_window"):
    title = "Deploy window active"
    color = "#f87171"
  else:
    title = "CME deploy window countdown"
    color = "#fbbf24"

  verify_cmd = window.get("verify_command") or ""
  deploy_cmd = window.get("deploy_command") or ""
  weekend_cmd = window.get("weekend_ops_command") or ""
  weekend_line = ""
  if weekend_cmd:
    weekend_line = f"<p class='muted' style='margin-top:0;font-family:monospace;font-size:0.8rem;'>{weekend_cmd}</p>"
  return f"""<div class="card" style="border-color:#854d0e;background:#1c1408;">
    <h2 style="color:{color};">{title}</h2>
    <p class="muted" style="margin-top:0;">{window.get("message", "")}</p>
    <p class="muted" style="margin-top:0;font-family:monospace;font-size:0.8rem;">{verify_cmd}</p>
    <p class="muted" style="margin-top:0;font-family:monospace;font-size:0.8rem;">{deploy_cmd}</p>
    {weekend_line}
  </div>"""


def build_cme_deploy_urgency(
  *,
  platform_revision_current: bool | None,
  cme_minutes_until_open: int | None,
  cme_in_session: bool = False,
) -> dict[str, Any] | None:
  """Surface deploy urgency on /api/status when CME is near and revision is behind."""
  if platform_revision_current is not False:
    return None
  if cme_in_session or cme_minutes_until_open is None:
    return None
  if cme_minutes_until_open > CME_DEPLOY_REMINDER_MINUTES:
    return None
  hours, mins = divmod(int(cme_minutes_until_open), 60)
  return {
    "active": True,
    "minutes_until_open": int(cme_minutes_until_open),
    "message": (
      f"CME reopen in {hours}h {mins}m — deploy before open for burst scan ordering "
      "and session-open auto-entry logging"
    ),
    "deploy_command": DEPLOY_COMMAND,
  }


def resolve_cme_deploy_reminder() -> dict[str, Any] | None:
  """Build deploy urgency during CME weekend prep, or None when not applicable."""
  import os

  from app.engines.gate_entry_guard import commodities_futures_weekend_closed, commodities_session_info

  if not commodities_futures_weekend_closed():
    return None
  cme_session = commodities_session_info()
  platform_revision = os.environ.get("PLATFORM_REVISION", "").strip() or None
  revision_current = (
    platform_revision == EXPECTED_PLATFORM_REVISION if platform_revision else None
  )
  return build_cme_deploy_urgency(
    platform_revision_current=revision_current,
    cme_minutes_until_open=cme_session.get("minutes_until_open"),
    cme_in_session=bool(cme_session.get("in_session")),
  )


def build_deploy_snapshot() -> dict[str, Any]:
  """Lightweight deploy + CME window snapshot (no DB, no Vercel/GitHub probes)."""
  from app.engines.gate_entry_guard import commodities_session_info
  from app.engines.intel_source_status import x_intel_collection_mode

  platform_revision = os.environ.get("PLATFORM_REVISION", "").strip() or None
  revision_current = (
    platform_revision == EXPECTED_PLATFORM_REVISION if platform_revision else None
  )
  cme_session = commodities_session_info()
  mins = cme_session.get("minutes_until_open")
  in_session = bool(cme_session.get("in_session"))
  return {
    "timestamp": datetime.utcnow().isoformat(),
    "platform_revision": platform_revision,
    "expected_platform_revision": EXPECTED_PLATFORM_REVISION,
    "platform_revision_current": revision_current,
    "github_token_configured": bool(os.environ.get("GITHUB_TOKEN", "").strip()),
    "cme_minutes_until_open": mins,
    "cme_in_session": in_session,
    "cme_deploy_window": build_cme_deploy_window(
      platform_revision_current=revision_current,
      cme_minutes_until_open=mins,
      cme_in_session=in_session,
    ),
    "cme_deploy_urgency": build_cme_deploy_urgency(
      platform_revision_current=revision_current,
      cme_minutes_until_open=mins,
      cme_in_session=in_session,
    ),
    "expected_dashboard_bundle": EXPECTED_DASHBOARD_BUNDLE,
    "dashboard_bundle_verify_command": DASHBOARD_BUNDLE_VERIFY_COMMAND,
    "weekend_ops_verify_command": WEEKEND_OPS_VERIFY_COMMAND,
    "wait_for_deploy_command": WAIT_FOR_DEPLOY_COMMAND,
    "run_deploy_window_command": RUN_DEPLOY_WINDOW_COMMAND,
    "x_intel_collection_mode": x_intel_collection_mode(),
  }


def build_deploy_credentials_nudges(
  *,
  github_token_configured: bool | None,
) -> list[str]:
  """Non-blocking deploy reminders (staleness checks, optional integrations)."""
  nudges: list[str] = []
  if github_token_configured is False:
    nudges.append("GITHUB_TOKEN missing on Render — deploy staleness checks incomplete")
  return nudges


def build_deploy_credentials_warnings(
  *,
  github_token_configured: bool | None = None,
  fomo_configured: bool = False,
  fomo_polling_active: bool = False,
  fomo_minutes_remaining: int | None = None,
) -> list[str]:
  """Blocking deploy credential issues (expired required integrations)."""
  _ = github_token_configured  # nudges only — kept for call-site compatibility
  warnings: list[str] = []
  if fomo_configured and not fomo_polling_active:
    label = f"{fomo_minutes_remaining}min" if fomo_minutes_remaining is not None else "expired"
    warnings.append(f"fomo bearer expired ({label})")
  return warnings


def resolve_fomo_bearer_nudge_tier(
  *,
  polling_active: bool,
  minutes_remaining: int | None,
) -> str | None:
  """Return nudge tier when bearer needs operator attention: 60, 15, or expired."""
  if not polling_active:
    return "expired"
  if minutes_remaining is None:
    return None
  if minutes_remaining <= 0:
    return "expired"
  if minutes_remaining <= 15:
    return "15"
  if minutes_remaining <= 60:
    return "60"
  return None


def fomo_bearer_nudge_message(tier: str, *, minutes_remaining: int | None = None) -> str:
  if tier == "expired":
    return "fomo.family bearer expired — memecoin intel paused"
  if tier == "15":
    label = f"{minutes_remaining}min" if minutes_remaining is not None else "soon"
    return f"fomo.family bearer expires in {label} — refresh before deploy window"
  if tier == "60":
    label = f"{minutes_remaining}min" if minutes_remaining is not None else "under 1h"
    return f"fomo.family bearer expires in {label} — schedule refresh"
  return ""


def format_deploy_credentials_crm_html(warnings: list[str]) -> str:
  """Render deploy credential warnings for the /crm landing page."""
  if not warnings:
    return ""
  items = "".join(f"<li>{item}</li>" for item in warnings)
  return f"""<div class="card" style="border-color:#7f1d1d;background:#1c0a0a;">
    <h2 style="color:#f87171;">Deploy credentials need attention</h2>
    <p class="muted" style="margin-top:0;">Resolve before tonight's Render deploy window:</p>
    <ul class="muted" style="margin:0.5rem 0 0 1rem;line-height:1.6;">{items}</ul>
    <p class="muted" style="margin-top:0.75rem;font-family:monospace;font-size:0.8rem;">
      bash trading-platform/scripts/check-deploy-credentials.sh<br>
      bash trading-platform/scripts/fomo-set-bearer.sh '&lt;bearer&gt;'<br>
      bash trading-platform/scripts/sync-render-env.sh
    </p>
  </div>"""


def apply_fomo_bearer_to_snapshot(
  snap: dict[str, Any],
  fomo: dict[str, Any],
) -> dict[str, Any]:
  """Merge fomo bearer polling state into deploy snapshot for ops scripts."""
  merged = dict(snap)
  configured = bool(fomo.get("configured"))
  polling = bool(fomo.get("polling_active"))
  merged["fomo_bearer_configured"] = configured
  merged["fomo_bearer_polling_active"] = polling
  merged["fomo_bearer_minutes_remaining"] = fomo.get("minutes_remaining")
  minutes = fomo.get("minutes_remaining")
  minutes_int = int(minutes) if isinstance(minutes, (int, float)) else None
  tier = resolve_fomo_bearer_nudge_tier(
    polling_active=polling,
    minutes_remaining=minutes_int,
  )
  merged["fomo_bearer_nudge_tier"] = tier
  merged["fomo_bearer_nudge_message"] = (
    fomo_bearer_nudge_message(tier, minutes_remaining=minutes_int) if tier else None
  )
  if configured and not polling:
    merged["fomo_bearer_refresh_hint"] = (
      "bash trading-platform/scripts/fomo-set-bearer.sh '<bearer>'"
    )
  warnings = build_deploy_credentials_warnings(
    github_token_configured=merged.get("github_token_configured"),
    fomo_configured=configured,
    fomo_polling_active=polling,
    fomo_minutes_remaining=merged.get("fomo_bearer_minutes_remaining"),
  )
  nudges = build_deploy_credentials_nudges(
    github_token_configured=merged.get("github_token_configured"),
  )
  merged["deploy_credentials_warnings"] = warnings
  merged["deploy_credentials_nudges"] = nudges
  merged["deploy_credentials_ready"] = len(warnings) == 0
  return merged


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
DEFAULT_VERIFIED_DASHBOARD_URL = "https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app"
DEFAULT_VERIFIED_DEPLOYMENT_ID = "dpl_HeAxy7WfML6rVo36R8RySA4DHagn"
VERCEL_TEAM_ID = "team_K7OUE7uroVXeVUf42cUAQvAl"
EXPECTED_DASHBOARD_BUNDLE = "2026-08-29-r101"
EXPECTED_PLATFORM_REVISION = "2026-08-29-r443"
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
  "2026-08-29-r46",
  "2026-08-29-r47",
  "2026-08-29-r48",
  "2026-08-29-r49",
  "2026-08-29-r50",
  "2026-08-29-r51",
  "2026-08-29-r52",
  "2026-08-29-r53",
  "2026-08-29-r55",
  "2026-08-29-r56",
  "2026-08-29-r57",
  "2026-08-29-r58",
  "2026-08-29-r59",
  "2026-08-29-r60",
  "2026-08-29-r61",
  "2026-08-29-r62",
  "2026-08-29-r63",
  "2026-08-29-r64",
  "2026-08-29-r65",
  "2026-08-29-r66",
  "2026-08-29-r67",
  "2026-08-29-r68",
  "2026-08-29-r69",
  "2026-08-29-r70",
  "2026-08-29-r71",
  "2026-08-29-r72",
  "2026-08-29-r73",
  "2026-08-29-r74",
  "2026-08-29-r75",
  "2026-08-29-r76",
  "2026-08-29-r77",
  "2026-08-29-r78",
  "2026-08-29-r79",
  "2026-08-29-r80",
  "2026-08-29-r81",
  "2026-08-29-r82",
  "2026-08-29-r83",
  "2026-08-29-r84",
  "2026-08-29-r85",
  "2026-08-29-r86",
  "2026-08-29-r87",
  "2026-08-29-r88",
  "2026-08-29-r89",
  "2026-08-29-r90",
  "2026-08-29-r91",
  "2026-08-29-r92",
  "2026-08-29-r93",
  "2026-08-29-r94",
  "2026-08-29-r95",
  "2026-08-29-r96",
  "2026-08-29-r97",
  "2026-08-29-r98",
  "2026-08-29-r99",
  "2026-08-29-r100",
  "2026-08-29-r101",
})


def configured_verified_dashboard_url() -> str:
  return os.environ.get("VERIFIED_DASHBOARD_URL", DEFAULT_VERIFIED_DASHBOARD_URL)


def configured_verified_deployment_id() -> str:
  return os.environ.get("VERIFIED_VERCEL_DEPLOYMENT_ID", DEFAULT_VERIFIED_DEPLOYMENT_ID)


def _vercel_hostname(url: str) -> str | None:
  cleaned = (url or "").strip().rstrip("/")
  if not cleaned:
    return None
  if "://" in cleaned:
    cleaned = cleaned.split("://", 1)[1]
  return cleaned.split("/", 1)[0] or None


async def resolve_vercel_promote_deployment_id(verified_url: str | None = None) -> str:
  """Resolve deployment id for Vercel alias promote — verified preview, not stale production."""
  url = (verified_url or configured_verified_dashboard_url()).strip()
  token = os.environ.get("VERCEL_TOKEN", "").strip()
  team_id = os.environ.get("VERCEL_ORG_ID", VERCEL_TEAM_ID).strip()
  hostname = _vercel_hostname(url)
  if token and hostname:
    try:
      async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(
          "https://api.vercel.com/v13/deployments/get",
          params={"url": hostname, "teamId": team_id},
          headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 200:
          deployment_id = response.json().get("id")
          if deployment_id:
            return deployment_id
    except Exception:
      pass
  return configured_verified_deployment_id()


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
  # Recent PR preview with SessionPrepBanner fast scan (r67).
  add("https://apex-trading-dashboard-o7tb7wydk-apexweb-adams-projects.vercel.app")
  # Newest main-branch previews — prefer before stale git-main alias.
  add("https://apex-trading-dashboard-43tumxweh-apexweb-adams-projects.vercel.app")
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
  global _discover_verified_cache, _discover_verified_cached_at
  now = time.monotonic()
  if (
    _discover_verified_cache is not None
    and (now - _discover_verified_cached_at) < DISCOVER_VERIFIED_CACHE_TTL_SECONDS
  ):
    return dict(_discover_verified_cache)

  configured_probe = await probe_configured_verified_dashboard()
  configured_url = configured_verified_dashboard_url()
  configured_rank = (configured_probe or {}).get("_rank", -1)

  best: dict[str, Any] | None = configured_probe
  best_rank = configured_rank

  urls_to_probe = [
    url
    for url in verified_dashboard_candidates()
    if not (url == configured_url and configured_probe)
  ]

  if urls_to_probe:
    probe_results = await asyncio.gather(
      *(probe_dashboard_config(url) for url in urls_to_probe),
      return_exceptions=True,
    )
    for url, cfg in zip(urls_to_probe, probe_results):
      if isinstance(cfg, Exception) or not cfg or not bundle_is_acceptable(cfg):
        continue
      rank = bundle_rank(cfg)
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
    result = best
  else:
    result = {
      "verified_dashboard_url": configured_url,
      "vercel_bundle_revision": None,
      "discovered": False,
    }

  _discover_verified_cache = dict(result)
  _discover_verified_cached_at = now
  return result


def clear_discover_verified_dashboard_cache() -> None:
  global _discover_verified_cache, _discover_verified_cached_at
  _discover_verified_cache = None
  _discover_verified_cached_at = 0.0


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
  promote_url = (
    "https://vercel.com/apexweb-adams-projects/apex-trading-dashboard/deployments"
  )

  try:
    prod_cfg = await probe_dashboard_config(PRODUCTION_DASHBOARD_URL)
    proxy_ok = await probe_production_proxy_operational()
    if prod_cfg and bundle_is_acceptable(prod_cfg) and proxy_ok:
      behind_expected = not bundle_is_current(prod_cfg)
      result: dict[str, Any] = {
        "vercel_bundle_stale": False,
        "vercel_bundle_behind_expected": behind_expected,
        "vercel_bundle_revision": prod_cfg.get("bundleRevision"),
        "production_proxy_operational": proxy_ok,
        "dashboard_url": PRODUCTION_DASHBOARD_URL,
        "expected_dashboard_bundle": EXPECTED_DASHBOARD_BUNDLE,
        "dashboard_bundle_verify_command": DASHBOARD_BUNDLE_VERIFY_COMMAND,
        "weekend_ops_verify_command": WEEKEND_OPS_VERIFY_COMMAND,
      }
      if behind_expected:
        discovered = await discover_verified_dashboard()
        verified_url = discovered["verified_dashboard_url"]
        result["verified_dashboard_url"] = verified_url
        result["verified_dashboard_discovered"] = discovered.get("discovered", False)
        result["verified_bundle_revision"] = discovered.get("vercel_bundle_revision")
        result["vercel_promote_deployment_id"] = await resolve_vercel_promote_deployment_id(verified_url)
        result["vercel_promote_url"] = promote_url
      return result

    discovered = await discover_verified_dashboard()
    verified_url = discovered["verified_dashboard_url"]
    dashboard_url = PRODUCTION_DASHBOARD_URL if proxy_ok else verified_url
    return {
      "vercel_bundle_stale": True,
      "vercel_bundle_behind_expected": True,
      "vercel_bundle_revision": (prod_cfg or {}).get("bundleRevision"),
      "production_proxy_operational": proxy_ok,
      "verified_dashboard_url": verified_url,
      "verified_dashboard_discovered": discovered.get("discovered", False),
      "verified_bundle_revision": discovered.get("vercel_bundle_revision"),
      "vercel_promote_deployment_id": await resolve_vercel_promote_deployment_id(verified_url),
      "vercel_promote_url": promote_url,
      "dashboard_url": dashboard_url,
      "expected_dashboard_bundle": EXPECTED_DASHBOARD_BUNDLE,
      "dashboard_bundle_verify_command": DASHBOARD_BUNDLE_VERIFY_COMMAND,
      "weekend_ops_verify_command": WEEKEND_OPS_VERIFY_COMMAND,
    }
  except Exception:
    verified_url = configured_verified_dashboard_url()
    proxy_ok = await probe_production_proxy_operational()
    return {
      "vercel_bundle_stale": True,
      "vercel_bundle_behind_expected": True,
      "production_proxy_operational": proxy_ok,
      "verified_dashboard_url": verified_url,
      "vercel_promote_deployment_id": await resolve_vercel_promote_deployment_id(verified_url),
      "vercel_promote_url": promote_url,
      "dashboard_url": PRODUCTION_DASHBOARD_URL if proxy_ok else verified_url,
      "expected_dashboard_bundle": EXPECTED_DASHBOARD_BUNDLE,
      "dashboard_bundle_verify_command": DASHBOARD_BUNDLE_VERIFY_COMMAND,
      "weekend_ops_verify_command": WEEKEND_OPS_VERIFY_COMMAND,
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
  if vercel.get("vercel_bundle_behind_expected"):
    verified = vercel.get("verified_dashboard_url", configured_verified_dashboard_url())
    promote_id = vercel.get("vercel_promote_deployment_id") or configured_verified_deployment_id()
    expected_bundle = vercel.get("expected_dashboard_bundle") or EXPECTED_DASHBOARD_BUNDLE
    prod_bundle = vercel.get("vercel_bundle_revision") or "unknown"
    if vercel.get("production_proxy_operational"):
      next_steps.append(
        "Vercel production bundle is behind expected "
        f"({prod_bundle} vs {expected_bundle}) but CRM proxy is operational on "
        f"{PRODUCTION_DASHBOARD_URL} — promote {promote_id} when deploy quota allows, "
        f"or use verified preview: {verified}"
      )
    elif vercel.get("vercel_bundle_stale"):
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


def dashboard_url_from_deploy(deploy_info: dict[str, Any]) -> str | None:
  """Pick dashboard URL from an existing deploy snapshot (no extra HTTP probes)."""
  if deploy_info.get("vercel_bundle_stale"):
    return deploy_info.get("verified_dashboard_url") or deploy_info.get("dashboard_url")
  return deploy_info.get("dashboard_url") or deploy_info.get("verified_dashboard_url")


async def resolve_crm_dashboard_url(deploy_info: dict[str, Any] | None = None) -> str:
  """Best CRM dashboard URL — one build_deploy_status when deploy_info is omitted.

  Reuses Vercel discovery from build_deploy_status instead of calling
  recommended_dashboard_url (which would probe verified previews again).
  """
  deploy = deploy_info if deploy_info is not None else await build_deploy_status()

  public = deploy.get("public_dashboard_url") or configured_public_dashboard_url()
  if public:
    cfg = await probe_dashboard_config(public)
    if cfg and bundle_is_acceptable(cfg):
      return public

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


_recommended_dashboard_cache: str | None = None
_recommended_dashboard_cached_at: float = 0.0
RECOMMENDED_DASHBOARD_CACHE_TTL_SECONDS = 120


def clear_recommended_dashboard_cache() -> None:
  global _recommended_dashboard_cache, _recommended_dashboard_cached_at
  _recommended_dashboard_cache = None
  _recommended_dashboard_cached_at = 0.0
  clear_discover_verified_dashboard_cache()


async def recommended_dashboard_url() -> str:
  """Return the best live CRM URL — public tunnel, then verified preview, then production."""
  global _recommended_dashboard_cache, _recommended_dashboard_cached_at
  now = time.monotonic()
  if (
    _recommended_dashboard_cache is not None
    and (now - _recommended_dashboard_cached_at) < RECOMMENDED_DASHBOARD_CACHE_TTL_SECONDS
  ):
    return _recommended_dashboard_cache

  result = await _recommended_dashboard_url_uncached()
  _recommended_dashboard_cache = result
  _recommended_dashboard_cached_at = now
  return result


async def _recommended_dashboard_url_uncached() -> str:
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
