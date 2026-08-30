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
    from app.engines.learning_engine import (
      build_crm_content_study_highlights,
      build_crm_learning_highlights,
    )
    from app.engines.intel_source_status import build_intel_sources
    from app.engines.crm_summary import build_crm_integration_hooks, build_crm_live_snapshot

    monday_recovery = await build_monday_recovery_summary(session)
    learning = await build_crm_learning_highlights(session)
    content_study = await build_crm_content_study_highlights(session)
    intel_sources = await build_intel_sources(session)
    live_snapshot = await build_crm_live_snapshot(session)
    integrations = await build_crm_integration_hooks(session)

  day = gate.get("verification_day", 0)
  trades = gate.get("total_trades", 0)
  wr = gate.get("win_rate", 0) or 0
  pnl = gate.get("total_pnl", 0) or 0
  pf = gate.get("profit_factor")
  pf_label = f"{pf:.2f}" if pf is not None else "n/a"
  rec = gate.get("recommendation", "")
  paused = gate.get("paused_bots") or []

  bot_rows = ""
  stocks_trade_count_nudge = bool(monday_recovery.get("stocks_trade_count_nudge"))
  commodities_graduation_nudge = bool(monday_recovery.get("commodities_graduation_nudge"))
  for bot_type, stats in per_bot.items():
    status = "shadow" if stats.get("paused") else "active"
    if stats.get("graduation_ready"):
      status = "ready"
    blockers = ", ".join(stats.get("graduation_blockers") or []) or "—"
    if bot_type == "stocks_futures" and stocks_trade_count_nudge:
      blockers = f"{blockers} · trade-count nudge active"
    if bot_type == "commodities" and commodities_graduation_nudge:
      blockers = f"{blockers} · graduation nudge active"
    wr_pct = (stats.get("win_rate") or 0) * 100
    bot_rows += (
      f"<tr><td>{bot_type}</td><td>{status}</td>"
      f"<td>{stats.get('total_trades', 0)}</td><td>{wr_pct:.0f}%</td>"
      f"<td>{blockers}</td></tr>"
    )

  recovery_rows = ""
  recovery_candidates = monday_recovery.get("recovery_candidates") or []
  recovery_nudge_note = ""
  if stocks_trade_count_nudge:
    stocks_bot = (monday_recovery.get("bots") or {}).get("stocks_futures") or {}
    stock_candidates = stocks_bot.get("recovery_candidates") or []
    candidate_label = ", ".join(stock_candidates) if stock_candidates else "proven winners"
    recovery_nudge_note = (
      f"<p class='muted' style='margin-top:0;color:#fbbf24;'>"
      f"Stocks shadow trade-count nudge: graduation WR met — easing proven-winner entries "
      f"for {candidate_label} (composite floor 0.34).</p>"
    )
  if commodities_graduation_nudge:
    commodities_bot = (monday_recovery.get("bots") or {}).get("commodities") or {}
    commodity_candidates = commodities_bot.get("recovery_candidates") or []
    candidate_label = ", ".join(commodity_candidates) if commodity_candidates else "recovery futures"
    recovery_nudge_note += (
      f"<p class='muted' style='margin-top:0;color:#fbbf24;'>"
      f"Commodities graduation nudge: active gate easing recovery entries for "
      f"{candidate_label} ahead of CME reopen.</p>"
    )
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
  recovery_table_body = recovery_rows or (
    "<tr><td colspan='4' class='muted'>No recovery-ready symbols right now — nudges still active.</td></tr>"
    if recovery_nudge_note
    else ""
  )

  redirect_seconds = 15 if (
    recovery_candidates
    or live_snapshot.get("positions")
    or recovery_nudge_note
    or monday_recovery.get("open_ready")
  ) else 3

  from app.engines.gate_entry_guard import (
    build_session_prep_status,
    commodities_session_info,
    stocks_session_info,
  )

  cme_session = commodities_session_info()
  stocks_session = stocks_session_info()
  session_prep = build_session_prep_status(
    stocks_session=stocks_session,
    commodities_session=cme_session,
    stocks_trade_count_nudge=stocks_trade_count_nudge,
    commodities_graduation_nudge=commodities_graduation_nudge,
    open_ready_rows=monday_recovery.get("open_ready"),
  )
  prep_lines: list[str] = []
  for bot_key, label in (("stocks_futures", "Stocks"), ("commodities", "Commodities")):
    entry = session_prep.get(bot_key) or {}
    if entry.get("prep_active"):
      mins = entry.get("minutes_until_open")
      hours_label = f"{mins // 60}h {mins % 60}m" if mins is not None else "soon"
      extended = "weekend TV prep · " if entry.get("extended_weekend_prep") else "TV prep · "
      nudge = entry.get("nudge_label") or "nudge"
      line = f"{label}: {extended}{nudge} — open in {hours_label}"
      ready = entry.get("open_ready_symbols") or []
      if ready:
        line += f" · open ready: {', '.join(ready)}"
      prep_lines.append(line)
  prep_summary = " · ".join(prep_lines)

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

  open_ready_card = ""
  open_ready_list = session_prep.get("open_ready") or []
  if open_ready_list:
    open_ready_table = ""
    for row in open_ready_list:
      bot_type = row.get("bot_type", "")
      symbol = row.get("symbol", "")
      composite = row.get("composite")
      composite_label = f"{composite:.3f}" if composite is not None else "—"
      direction = row.get("direction") or "—"
      macd = row.get("macd") or "—"
      mins = row.get("minutes_until_open")
      countdown = f"{mins // 60}h {mins % 60}m" if mins is not None else "soon"
      blockers = ", ".join(row.get("blockers") or []) or "—"
      gate_skip = " · gate-skip" if row.get("monday_gate_skip_ready") else ""
      open_ready_table += (
        f"<tr><td>{bot_type}</td><td><strong>{symbol}</strong></td>"
        f"<td>{composite_label}</td><td>{direction}</td><td>{macd}</td>"
        f"<td>{countdown}</td>"
        f"<td>{blockers}{gate_skip}</td></tr>"
      )
    open_ready_card = f"""<div class="card recovery">
    <h2>Session open ready</h2>
    <p class="muted" style="margin-top:0;">Gate-skip eligible — auto-entry when session opens.</p>
    <table>
      <thead><tr><th>Bot</th><th>Symbol</th><th>Composite</th><th>Signal</th><th>MACD</th><th>Opens in</th><th>Blockers</th></tr></thead>
      <tbody>{open_ready_table}</tbody>
    </table>
  </div>"""

  commodities_prep = session_prep.get("commodities") or {}
  stocks_prep = session_prep.get("stocks_futures") or {}

  def _session_countdown(mins: int | None) -> str:
    if mins is None:
      return "soon"
    return f"{mins // 60}h {mins % 60}m"

  next_session_lines: list[str] = []
  if not cme_session.get("in_session"):
    cme_mins = cme_session.get("minutes_until_open")
    comm_ready = ", ".join(commodities_prep.get("open_ready_symbols") or []) or "—"
    comm_scan = "5s" if commodities_prep.get("gate_reopen_imminent") else (
      "15s" if commodities_prep.get("gate_fast_scan_active") else "30s"
    )
    next_session_lines.append(
      f"<strong>CME reopen</strong> in {_session_countdown(cme_mins)} · prep scan {comm_scan} · open ready: {comm_ready}"
    )
  if not stocks_session.get("in_session"):
    us_mins = stocks_session.get("minutes_until_open")
    stocks_ready = ", ".join(stocks_prep.get("open_ready_symbols") or []) or "—"
    stocks_scan = "5s" if stocks_prep.get("gate_reopen_imminent") else (
      "15s" if stocks_prep.get("gate_fast_scan_active") else "30s"
    )
    next_session_lines.append(
      f"<strong>US stocks open</strong> in {_session_countdown(us_mins)} · prep scan {stocks_scan} · open ready: {stocks_ready}"
    )
  next_sessions_card = ""
  if next_session_lines:
    body = "".join(f"<p class='muted' style='margin:0.35rem 0 0;'>{line}</p>" for line in next_session_lines)
    auto_entry_note = ""
    if commodities_prep.get("open_ready_symbols") or stocks_prep.get("open_ready_symbols"):
      auto_entry_note = (
        "<p class='muted' style='margin:0.5rem 0 0;color:#86efac;'>"
        "Gate-skip eligible — bots auto-enter when session opens.</p>"
      )
    auto_entry_details = ""
    detail_rows = (commodities_prep.get("open_ready_details") or []) + (
      stocks_prep.get("open_ready_details") or []
    )
    if detail_rows:
      detail_table = ""
      for row in detail_rows:
        symbol = row.get("symbol", "")
        composite = row.get("composite")
        composite_label = f"{composite:.3f}" if composite is not None else "—"
        direction = row.get("direction") or "—"
        macd = row.get("macd") or "—"
        blockers = ", ".join(row.get("blockers") or []) or "—"
        gate_skip = "yes" if row.get("monday_gate_skip_ready") else "no"
        detail_table += (
          f"<tr><td><strong>{symbol}</strong></td><td>{composite_label}</td>"
          f"<td>{direction}</td><td>{macd}</td><td>{blockers}</td><td>{gate_skip}</td></tr>"
        )
      floor_note = ""
      if commodities_prep.get("nudge_active"):
        from app.engines.gate_entry_guard import commodities_recovery_composite_floor

        cme_floor = commodities_recovery_composite_floor(graduation_nudge=True)
        floor_note = (
          f"<p class='muted' style='margin:0.35rem 0 0;font-size:0.8rem;'>"
          f"Commodities composite floor: {cme_floor:.2f}</p>"
        )
      auto_entry_details = f"""<table style="margin-top:0.75rem;">
      <thead><tr><th>Symbol</th><th>Composite</th><th>Signal</th><th>MACD</th><th>Blockers</th><th>Gate-skip</th></tr></thead>
      <tbody>{detail_table}</tbody>
    </table>{floor_note}"""
    next_sessions_card = f"""<div class="card" style="border-color:#1e3a5f;background:#0c1929;">
    <h2 style="color:#60a5fa;font-size:1rem;margin:0 0 0.35rem;">Next sessions</h2>
    {body}
    {auto_entry_note}
    {auto_entry_details}
  </div>"""

  cme_mins = cme_session.get("minutes_until_open")
  cme_imminent_banner = ""
  if not cme_session.get("in_session") and cme_mins is not None and cme_mins <= 60:
    ready = ", ".join(commodities_prep.get("open_ready_symbols") or []) or "—"
    auto_entry = ", ".join(commodities_prep.get("open_ready_symbols") or [])
    scan_label = "5s" if commodities_prep.get("gate_reopen_imminent") else "15s"
    wake_note = " · TV wake active" if commodities_prep.get("reopen_wake_active") else ""
    auto_entry_note = (
      f"<p class='muted' style='margin-top:0.35rem;color:#86efac;'>"
      f"Gate-skip auto-entry queued: {auto_entry}</p>"
      if auto_entry
      else ""
    )
    cme_imminent_banner = f"""<div class="card" style="border-color:#b45309;background:#451a03;">
    <p style="color:#fbbf24;font-weight:600;margin:0;">CME reopen imminent — {cme_mins}m until open{wake_note}</p>
    <p class="muted" style="margin-top:0.5rem;">Fast scan {scan_label} · open ready: {ready}</p>
    {auto_entry_note}
  </div>"""

  us_mins = stocks_session.get("minutes_until_open")
  us_imminent_banner = ""
  if not stocks_session.get("in_session") and us_mins is not None and us_mins <= 60:
    ready = ", ".join(stocks_prep.get("open_ready_symbols") or []) or "—"
    auto_entry = ", ".join(stocks_prep.get("open_ready_symbols") or [])
    scan_label = "5s" if stocks_prep.get("gate_reopen_imminent") else "15s"
    wake_note = " · TV wake active" if stocks_prep.get("reopen_wake_active") else ""
    auto_entry_note = (
      f"<p class='muted' style='margin-top:0.35rem;color:#86efac;'>"
      f"Gate-skip auto-entry queued: {auto_entry}</p>"
      if auto_entry
      else ""
    )
    us_imminent_banner = f"""<div class="card" style="border-color:#b45309;background:#451a03;">
    <p style="color:#fbbf24;font-weight:600;margin:0;">US stocks open imminent — {us_mins}m until open{wake_note}</p>
    <p class="muted" style="margin-top:0.5rem;">Fast scan {scan_label} · open ready: {ready}</p>
    {auto_entry_note}
  </div>"""

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

  content_rows = ""
  for row in content_study.get("recent") or []:
    source_type = row.get("source_type", "")
    title = row.get("title", "")
    impact = row.get("impact") or "—"
    confidence = row.get("confidence") or 0
    applied = "applied" if row.get("applied") else "pending"
    content_rows += (
      f"<div class='learning-item'><strong>{source_type}</strong> — {title}<br>"
      f"<span class='muted'>Impact: {impact}</span><br>"
      f"<span class='muted'>Confidence {confidence:.0%} · {applied}</span></div>"
    )

  content_summary = (
    f"{content_study.get('insights_applied', 0)} insights applied to strategy · "
    "content study every 2h"
  )

  intel_active = sum(1 for s in intel_sources if s.get("status") in ("active", "degraded"))
  intel_total = len(intel_sources)
  intel_degraded = [s["source"] for s in intel_sources if s.get("status") == "degraded"]
  intel_footer = f"intel {intel_active}/{intel_total} sources"
  if intel_degraded:
    intel_footer += f" ({', '.join(intel_degraded)} degraded)"

  position_rows = ""
  total_unrealized = 0.0
  for row in live_snapshot.get("positions") or []:
    pnl = row.get("unrealized_pnl") or 0
    total_unrealized += pnl
    pnl_class = "pnl-pos" if pnl >= 0 else "pnl-neg"
    gate_tag = "gate" if row.get("is_active_gate") else "shadow"
    position_rows += (
      f"<tr><td>{row.get('bot_type')}</td><td><strong>{row.get('symbol')}</strong></td>"
      f"<td>{row.get('side')}</td><td>{row.get('entry_price', 0):,.2f}</td>"
      f"<td>{row.get('current_price', 0):,.2f}</td>"
      f"<td class='{pnl_class}'>${pnl:,.2f}</td><td>{gate_tag}</td></tr>"
    )

  tightening = live_snapshot.get("gate_tightening") or {}
  blocked_entries = ", ".join(tightening.get("blocked_new_entries") or []) or "none"
  proven_winners = live_snapshot.get("proven_winner_symbols") or {}
  proven_labels = []
  for bot_type, symbols in proven_winners.items():
    if symbols:
      proven_labels.append(f"{bot_type}: {', '.join(symbols[:4])}")
  proven_summary = " · ".join(proven_labels) if proven_labels else "—"
  live_summary = (
    f"Active gate: {', '.join(live_snapshot.get('active_bots') or [])} · "
    f"unrealized ${total_unrealized:,.2f} · "
    f"MACD bullish required: {'yes' if tightening.get('require_macd_bullish') else 'no'}"
  )

  tv = integrations.get("tradingview") or {}
  pm = integrations.get("polymarket") or {}
  wt = integrations.get("wallet_tracker") or {}
  fomo = integrations.get("fomo") or {}
  axiom = integrations.get("axiom") or {}
  phantom = integrations.get("phantom") or {}

  intel_alert_banner = ""
  if fomo.get("bearer_configured") and not fomo.get("bearer_polling_active"):
    intel_alert_banner = f"""<div class="card" style="border-color:#b45309;background:#451a03;">
    <p style="color:#fbbf24;font-weight:600;margin:0;">fomo.family bearer expired — memecoin intel paused</p>
    <p class="muted" style="margin-top:0.5rem;">Open fomo.family with Tampermonkey bridge or run <code>./trading-platform/scripts/fomo-set-bearer.sh 'eyJ...'</code></p>
  </div>"""
  elif intel_degraded:
    intel_alert_banner = f"""<div class="card" style="border-color:#854d0e;background:#292524;">
    <p style="color:#fbbf24;font-weight:600;margin:0;">Intel degraded: {', '.join(intel_degraded)}</p>
    <p class="muted" style="margin-top:0.5rem;">Check integrations below — trading continues on active sources.</p>
  </div>"""

  tv_status = "configured" if tv.get("configured") else "not configured"
  pm_status = "wallet + API" if pm.get("wallet_configured") and pm.get("api_configured") else (
    "wallet only" if pm.get("wallet_configured") else "API only" if pm.get("api_configured") else "not configured"
  )
  if fomo.get("bearer_configured"):
    mins = fomo.get("bearer_minutes_remaining")
    if fomo.get("bearer_polling_active"):
      fomo_status = f"poll active ({mins} min left)" if mins is not None else "poll active"
    else:
      fomo_status = "bearer expired — open fomo.family + Tampermonkey or run fomo-set-bearer.sh"
  elif fomo.get("configured"):
    fomo_status = "webhook ready"
  else:
    fomo_status = "off"
  if axiom.get("multi_wallet_ready"):
    mode = axiom.get("poll_mode") or "mirror"
    axiom_status = f"multi-wallet ({axiom.get('tracked_wallets') or 8}+) · {mode} poll"
  elif axiom.get("configured"):
    axiom_status = "webhook ready"
  else:
    axiom_status = "off"
  if axiom.get("session_polling_active"):
    axiom_status += " · session poll active"
  elif axiom.get("session_configured"):
    axiom_status += " · session expired"
  phantom_status = "webhook ready" if phantom.get("configured") else "off"
  if phantom.get("portfolio_poll"):
    wallets = phantom.get("tracked_wallets") or 8
    default_tag = " (default whales)" if phantom.get("using_default_wallets") else ""
    mode = phantom.get("portfolio_poll_mode") or "rpc"
    phantom_status = f"{mode} poll active · {wallets} wallets{default_tag}"
  elif phantom.get("configured"):
    phantom_status = "webhook ready — Helius poll waiting on HELIUS_API_KEY"
  fomo_bearer_note = ""
  if fomo.get("bearer_configured"):
    expires = fomo.get("bearer_expires_at") or "unknown"
    polling = "yes" if fomo.get("bearer_polling_active") else "no"
    fomo_bearer_note = (
      f"<p class='muted' style='margin-top:0;'>fomo server poll: {polling} · expires {expires}</p>"
    )
  integration_health_note = ""
  if fomo.get("bearer_configured") and not fomo.get("bearer_polling_active"):
    integration_health_note = (
      "<p style='color:#fbbf24;margin:0.5rem 0;'>"
      "fomo.family bearer expired — memecoin copy-trade intel paused. "
      "Open fomo.family with Tampermonkey bridge or run "
      "<code>./trading-platform/scripts/fomo-set-bearer.sh 'eyJ...'</code>"
      "</p>"
    )
  integrations_summary = (
    f"TradingView {tv_status} ({tv.get('items', 0)} alerts) · "
    f"Polymarket {pm_status} ({pm.get('intel_items', 0)} markets) · "
    f"Wallet tracker {'on' if wt.get('configured') else 'off'} · "
    f"fomo.family {fomo_status} · "
    f"axiom.trade {axiom_status} · "
    f"Phantom {phantom_status}"
  )
  pm_profile = pm.get("profile_url") or ""
  pm_profile_link = (
    f"<p class='muted' style='margin-top:0;'><a href='{pm_profile}'>Polymarket profile</a></p>"
    if pm_profile
    else ""
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
  <meta http-equiv="refresh" content="60">
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
    .live {{ border-color: #4c1d95; background: #1a1033; }}
    .live h2 {{ color: #c4b5fd; font-size: 1rem; margin: 0 0 0.5rem; }}
    .pnl-pos {{ color: #4ade80; }}
    .pnl-neg {{ color: #f87171; }}
    .integrations {{ border-color: #713f12; background: #1c1407; }}
    .integrations h2 {{ color: #fbbf24; font-size: 1rem; margin: 0 0 0.5rem; }}
    .tag-ok {{ color: #4ade80; }}
    .tag-off {{ color: #888; }}
</head>
<body>
  <h1>Apex Trading CRM</h1>
  <p>Paper trading · 4 autonomous bots · Real-time WebSocket</p>
  <p class="muted" style="margin-top:0;">{session_summary}</p>
  {f"<p class='muted' style='margin-top:0;color:#fbbf24;'>{prep_summary}</p>" if prep_summary else ""}
  {intel_alert_banner}
  {next_sessions_card}
  {cme_imminent_banner}
  {us_imminent_banner}
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
  {f"""<div class="card live">
    <h2>Live gate positions</h2>
    <p class="muted" style="margin-top:0;">{live_summary}</p>
    <table>
      <thead><tr><th>Bot</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Mark</th><th>PnL</th><th>Mode</th></tr></thead>
      <tbody>{position_rows}</tbody>
    </table>
    <p class="muted" style="margin-top:0.75rem;">Blocked entries: {blocked_entries}</p>
    <p class="muted" style="margin-top:0;">Proven winners: {proven_summary}</p>
  </div>""" if position_rows else ""}
  {open_ready_card}
  {f"""<div class="card recovery">
    <h2>Monday recovery watchlist</h2>
    <p class="muted" style="margin-top:0;">Recovery-ready symbols across commodities and stocks shadow bots.</p>
    {recovery_nudge_note}
    <table>
      <thead><tr><th>Bot</th><th>Symbol</th><th>Composite</th><th>Blockers</th></tr></thead>
      <tbody>{recovery_table_body}</tbody>
    </table>
  </div>""" if recovery_table_body or recovery_nudge_note else ""}
  {f"""<div class="card learning">
    <h2>Today's learning loop</h2>
    <p class="muted" style="margin-top:0;">{learning_summary}</p>
    {learning_rows if learning_rows else "<p class='muted'>No losing-trade patterns today — bots scanning.</p>"}
  </div>""" if learning else ""}
  {f"""<div class="card learning">
    <h2>External content study</h2>
    <p class="muted" style="margin-top:0;">{content_summary}</p>
    {content_rows if content_rows else "<p class='muted'>No recent insights — next study cycle within 1 hour.</p>"}
  </div>""" if content_study else ""}
  <div class="card integrations">
    <h2>TradingView, Polymarket, fomo, axiom &amp; Phantom hooks</h2>
    {integration_health_note}
    <p class="muted" style="margin-top:0;">{integrations_summary}</p>
    <p class="muted" style="margin-top:0;">TV webhook: <code>{tv.get('webhook_url', '')}</code></p>
    <p class="muted" style="margin-top:0;">Wallet webhook: <code>{wt.get('webhook_url', '')}</code></p>
    <p class="muted" style="margin-top:0;">fomo webhook: <code>{fomo.get('webhook_url', '')}</code></p>
    <p class="muted" style="margin-top:0;">fomo userscript (Tampermonkey): <a href="{fomo.get('userscript_url', '')}">{fomo.get('userscript_url', '')}</a></p>
    {fomo_bearer_note}
    <p class="muted" style="margin-top:0;">axiom webhook: <code>{axiom.get('webhook_url', '')}</code></p>
    <p class="muted" style="margin-top:0;">axiom userscript: <a href="{axiom.get('userscript_url', '')}">{axiom.get('userscript_url', '')}</a> · min {axiom.get('min_wallets_required', 8)} wallets</p>
    <p class="muted" style="margin-top:0;">Phantom webhook: <code>{phantom.get('webhook_url', '')}</code> — {phantom.get('note', 'forward portfolio via webhook')}</p>
    <p class="muted" style="margin-top:0;">Phantom userscript: <a href="{phantom.get('userscript_url', '')}">{phantom.get('userscript_url', '')}</a> · portfolio poll: {'on (' + str(phantom.get('portfolio_poll_mode', 'off')) + ')' if phantom.get('portfolio_poll') else 'off'}</p>
    {pm_profile_link}
  </div>
  <p><a href="{url}">Open live dashboard →</a> <span class="muted">(redirecting in {redirect_seconds}s)</span></p>
  <p class="muted">{deploy_note}</p>
  {backend_note}
  <p class="muted ok">● Platform running — {intel_footer} · learning active</p>
</body>
</html>"""
  return HTMLResponse(content=html, status_code=200, headers={"Refresh": f"{redirect_seconds}; url={url}"})
