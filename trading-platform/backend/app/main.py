import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.routes import router
from app.config import settings
from app.engines.deploy_status import (
  EXPECTED_DASHBOARD_BUNDLE,
  build_deploy_status,
  recommended_dashboard_url,
)
from app.workers.scheduler import setup_scheduler, stop_bots


@asynccontextmanager
async def lifespan(app: FastAPI):
  from app.database import is_postgres

  commit = settings.render_git_commit or os.environ.get("RENDER_GIT_COMMIT") or "unknown"
  revision = os.environ.get("PLATFORM_REVISION", "unknown")
  on_render = bool(os.environ.get("RENDER"))
  print(
    f"[Startup] {settings.app_name} commit={commit[:12]} "
    f"revision={revision} paper_only={settings.paper_trading_only} "
    f"db={'postgres' if is_postgres() else 'sqlite'}"
  )
  if on_render and not is_postgres():
    print(
      "[Startup] WARNING: Render is using ephemeral SQLite — gate data resets on every deploy. "
      "Set DATABASE_URL to Supabase (see SUPABASE_SETUP.md) and run scripts/sync-render-env.sh"
    )
  await setup_scheduler()
  yield
  stop_bots()


app = FastAPI(
  title=settings.app_name,
  description="Multi-market paper trading platform with AI learning",
  version="1.0.0",
  lifespan=lifespan,
)

origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
  CORSMiddleware,
  allow_origins=origins + ["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
async def root():
  deploy = await build_deploy_status()
  dashboard = deploy.get("dashboard_url")
  return {
    "name": settings.app_name,
    "mode": "paper_trading" if settings.paper_trading_only else "live",
    "docs": "/docs",
    "api": "/api",
    "dashboard": dashboard,
    "dashboard_redirect": "/api/dashboard",
    "crm_landing": "/crm",
  }


@app.api_route("/dashboard", methods=["GET", "HEAD"], include_in_schema=False)
async def root_dashboard_redirect():
  url = await recommended_dashboard_url()
  return RedirectResponse(url=url, status_code=302)


@app.api_route("/crm", methods=["GET", "HEAD"], include_in_schema=False)
async def crm_landing():
  from app.database import SessionLocal
  from app.engines.profitability_gate import ProfitabilityGate

  url = await recommended_dashboard_url()
  deploy = await build_deploy_status()
  stale = deploy.get("vercel_bundle_stale")
  proxy_ok = deploy.get("production_proxy_operational")
  promote_id = deploy.get("vercel_promote_deployment_id") or "dpl_DMSgUEGsa2PTokNr99BXWoggczd7"

  async with SessionLocal() as session:
    gate_engine = ProfitabilityGate(session)
    gate = await gate_engine.evaluate()
    per_bot = await gate_engine.evaluate_per_bot()
    from app.engines.scan_preview import build_monday_recovery_summary
    from app.engines.learning_engine import build_crm_learning_highlights

    monday_recovery = await build_monday_recovery_summary(session)
    learning = await build_crm_learning_highlights(session)

  day = gate.get("verification_day", 0)
  trades = gate.get("total_trades", 0)
  wr = gate.get("win_rate", 0) or 0
  pnl = gate.get("total_pnl", 0) or 0
  pf = gate.get("profit_factor")
  pf_label = f"{pf:.2f}" if pf is not None else "n/a"
  rec = gate.get("recommendation", "")
  paused = gate.get("paused_bots") or []

  bot_rows = ""
  for bot_type, stats in per_bot.items():
    status = "shadow" if stats.get("paused") else "active"
    if stats.get("graduation_ready"):
      status = "ready"
    blockers = ", ".join(stats.get("graduation_blockers") or []) or "—"
    wr_pct = (stats.get("win_rate") or 0) * 100
    bot_rows += (
      f"<tr><td>{bot_type}</td><td>{status}</td>"
      f"<td>{stats.get('total_trades', 0)}</td><td>{wr_pct:.0f}%</td>"
      f"<td>{blockers}</td></tr>"
    )

  recovery_rows = ""
  recovery_candidates = monday_recovery.get("recovery_candidates") or []
  for row in monday_recovery.get("all") or []:
    bot_type = row.get("bot_type", "")
    symbol = row.get("symbol", "")
    composite = row.get("composite")
    composite_label = f"{composite:.3f}" if composite is not None else "—"
    blockers = ", ".join(row.get("blockers") or []) or "—"
    recovery_rows += (
      f"<tr><td>{bot_type}</td><td><strong>{symbol}</strong></td>"
      f"<td>{composite_label}</td><td>{blockers}</td></tr>"
    )

  redirect_seconds = 15 if recovery_candidates else 3

  from app.engines.gate_entry_guard import commodities_session_info, stocks_session_info

  cme_session = commodities_session_info()
  stocks_session = stocks_session_info()
  session_lines: list[str] = []
  if not cme_session.get("in_session"):
    mins = cme_session.get("minutes_until_open")
    if mins is not None:
      session_lines.append(f"CME futures reopen in {mins // 60}h {mins % 60}m ({cme_session.get('mode', '')})")
  else:
    session_lines.append("CME futures session open")
  if not stocks_session.get("in_session"):
    mins = stocks_session.get("minutes_until_open")
    if mins is not None:
      session_lines.append(f"US stocks open in {mins // 60}h {mins % 60}m ({stocks_session.get('mode', '')})")
  else:
    session_lines.append("US stocks session open")
  session_summary = " · ".join(session_lines)

  learning_rows = ""
  learning_reviews = learning.get("reviews") or []
  for row in learning_reviews:
    bot_type = row.get("bot_type", "")
    trades = row.get("total_trades", 0)
    losses = row.get("losing_trades", 0)
    wr_pct = (row.get("win_rate") or 0) * 100
    pnl_val = row.get("net_pnl") or 0
    patterns = row.get("patterns_found") or "—"
    changes = row.get("strategy_changes") or "—"
    learning_rows += (
      f"<div class='learning-item'><strong>{bot_type}</strong> — "
      f"{trades} trades ({losses}L) · {wr_pct:.0f}% WR · ${pnl_val:,.2f}<br>"
      f"<span class='muted'>Patterns: {patterns}</span><br>"
      f"<span class='muted'>Changes: {changes}</span></div>"
    )

  learning_summary = (
    f"{learning.get('trade_analyses', 0)} post-mortems · "
    f"{learning.get('pending_insights', 0)} pending insights · "
    f"review date {learning.get('review_date', '')}"
  )

  if stale and url == deploy.get("verified_dashboard_url"):
    bundle_label = deploy.get("verified_bundle_revision") or EXPECTED_DASHBOARD_BUNDLE
    deploy_note = (
      f"Redirecting to verified preview with CRM bundle ({bundle_label}). "
      f"Promote {promote_id} in Vercel to restore the -flame production alias."
    )
  elif stale and proxy_ok:
    deploy_note = (
      f"Production CRM proxy on -flame is operational but bundle is stale. "
      f"Promote {promote_id} in Vercel for native routes and newest UI."
    )
  elif stale:
    deploy_note = f"Production Vercel bundle is stale. Promote {promote_id} in Vercel when ready."
  else:
    deploy_note = "Production dashboard bundle is current."

  backend_stale = deploy.get("is_stale")
  backend_note = ""
  if backend_stale:
    running = (deploy.get("git_commit") or "?")[:12]
    latest = (deploy.get("latest_main_commit") or "?")[:12]
    backend_note = (
      f"<p class='muted' style='color:#fbbf24;'>Backend deploy stale — running {running}, main is {latest}. "
      "Manual deploy in Render or set RENDER_DEPLOY_HOOK.</p>"
    )

  html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="refresh" content="{redirect_seconds};url={url}" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Apex Trading CRM</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #0a0a0f; color: #e5e5e5; padding: 2rem; max-width: 42rem; margin: 0 auto; }}
    h1 {{ color: #d4af37; margin-bottom: 0.25rem; }}
    .card {{ background: #12121a; border: 1px solid #2a2a35; border-radius: 0.75rem; padding: 1rem 1.25rem; margin: 1.25rem 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; }}
    .stat {{ font-size: 1.25rem; font-weight: 600; }}
    .label {{ font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.05em; }}
    a {{ color: #d4af37; }}
    .muted {{ color: #888; font-size: 0.85rem; margin-top: 1rem; line-height: 1.5; }}
    .ok {{ color: #4ade80; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 0.75rem; }}
    th, td {{ text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid #2a2a35; }}
    th {{ color: #888; font-weight: 500; }}
    .tag-shadow {{ color: #fbbf24; }}
    .recovery {{ border-color: #166534; background: #052e16; }}
    .recovery h2 {{ color: #4ade80; font-size: 1rem; margin: 0 0 0.5rem; }}
    .learning {{ border-color: #1e3a5f; background: #0c1929; }}
    .learning h2 {{ color: #60a5fa; font-size: 1rem; margin: 0 0 0.5rem; }}
    .learning-item {{ margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #2a2a35; }}
    .learning-item:first-of-type {{ border-top: none; padding-top: 0; margin-top: 0; }}
</head>
<body>
  <h1>Apex Trading CRM</h1>
  <p>Paper trading · 4 autonomous bots · Real-time WebSocket</p>
  <p class="muted" style="margin-top:0;">{session_summary}</p>
  <div class="card">
    <p class="label">30-day verification gate · day {day}/30</p>
    <div class="grid">
      <div><div class="label">Trades</div><div class="stat">{trades}/100</div></div>
      <div><div class="label">Win rate</div><div class="stat">{wr * 100:.1f}%</div></div>
      <div><div class="label">Profit factor</div><div class="stat">{pf_label}</div></div>
      <div><div class="label">PnL</div><div class="stat">${pnl:,.2f}</div></div>
    </div>
    <p class="muted" style="margin-top: 1rem;">{rec}</p>
    {f"<p class='muted'>Paused from active gate: {', '.join(paused)}</p>" if paused else ""}
    <table>
      <thead><tr><th>Bot</th><th>Status</th><th>Trades</th><th>WR</th><th>Graduation</th></tr></thead>
      <tbody>{bot_rows}</tbody>
    </table>
  </div>
  {f"""<div class="card recovery">
    <h2>Monday recovery watchlist</h2>
    <p class="muted" style="margin-top:0;">Recovery-ready symbols across commodities and stocks shadow bots.</p>
    <table>
      <thead><tr><th>Bot</th><th>Symbol</th><th>Composite</th><th>Blockers</th></tr></thead>
      <tbody>{recovery_rows}</tbody>
    </table>
  </div>""" if recovery_rows else ""}
  {f"""<div class="card learning">
    <h2>Today's learning loop</h2>
    <p class="muted" style="margin-top:0;">{learning_summary}</p>
    {learning_rows if learning_rows else "<p class='muted'>No losing-trade patterns today — bots scanning.</p>"}
  </div>""" if learning else ""}
  <p><a href="{url}">Open live dashboard →</a> <span class="muted">(redirecting in {redirect_seconds}s)</span></p>
  <p class="muted">{deploy_note}</p>
  {backend_note}
  <p class="muted ok">● Platform running — intel 10/10 sources · learning active</p>
</body>
</html>"""
  return HTMLResponse(content=html, status_code=200, headers={"Refresh": f"{redirect_seconds}; url={url}"})
