import asyncio
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings, BOT_TYPES
from app.database import SessionLocal, get_db, is_postgres
from app.intelligence.wallet_tracker import wallet_tracker_configured
from app.engines.deploy_status import build_deploy_status, resolve_crm_dashboard_url
from app.engines.learning_engine import serialize_learning_insight
from app.engines.profitability_gate import ProfitabilityGate
from app.engines.trade_stats import aggregate_win_rate
from app.engines.verification_snapshot import serialize_verification_snapshot
from app.models.entities import (
  BotState,
  DailyReview,
  IntelligenceItem,
  LearningInsight,
  Portfolio,
  Position,
  StrategyConfig,
  Trade,
  TradeAnalysis,
  VerificationSnapshot,
)

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
  return {"status": "ok", "mode": "paper_trading", "timestamp": datetime.utcnow().isoformat()}


@router.get("/deploy/snapshot")
async def get_deploy_snapshot(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Fast deploy revision + CME window timing for ops scripts (no heavy status build)."""
  from app.engines.deploy_status import (
    apply_fomo_bearer_to_snapshot,
    apply_learning_to_snapshot,
    build_deploy_snapshot,
  )
  from app.engines.learning_engine import build_crm_content_study_highlights
  from app.engines.platform_status import _fetch_learning_counts
  from app.intelligence.fomo_tracker import get_fomo_bearer_status

  snap = build_deploy_snapshot()
  fomo = await get_fomo_bearer_status(db)
  learning = await _fetch_learning_counts(db)
  content_study = await build_crm_content_study_highlights(db)
  return apply_learning_to_snapshot(
    apply_fomo_bearer_to_snapshot(snap, fomo),
    learning=learning,
    content_study=content_study,
  )


@router.get("/platform-urls")
async def get_platform_urls() -> dict[str, Any]:
  """Public CRM/API URLs when running via Cloud Agent tunnels."""
  from app.engines.deploy_status import (
    configured_public_backend_url,
    configured_public_dashboard_url,
    recommended_dashboard_url,
  )

  dashboard = configured_public_dashboard_url()
  backend = configured_public_backend_url()
  recommended = await recommended_dashboard_url()
  ws = None
  if backend:
    ws = backend.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws"
  return {
    "dashboard_url": dashboard,
    "backend_url": backend,
    "backend_ws": ws,
    "recommended_dashboard_url": recommended,
    "source": "env" if os.environ.get("PUBLIC_DASHBOARD_URL") else ("platform-urls.json" if dashboard else None),
  }


@router.get("/dashboard-url")
async def get_dashboard_url() -> dict[str, Any]:
  """Canonical CRM dashboard URL — verified preview when Vercel production bundle is stale."""
  deploy = await build_deploy_status()
  recommended = await resolve_crm_dashboard_url(deploy)
  return {
    "recommended_url": recommended,
    "production_url": "https://apex-trading-dashboard-flame.vercel.app",
    "verified_preview_url": deploy.get("verified_dashboard_url"),
    "vercel_bundle_stale": deploy.get("vercel_bundle_stale"),
    "vercel_bundle_revision": deploy.get("vercel_bundle_revision"),
    "vercel_promote_deployment_id": deploy.get("vercel_promote_deployment_id"),
    "vercel_promote_url": deploy.get("vercel_promote_url"),
    "verified_dashboard_discovered": deploy.get("verified_dashboard_discovered"),
    "verified_bundle_revision": deploy.get("verified_bundle_revision"),
    "production_proxy_operational": deploy.get("production_proxy_operational"),
    "next_steps": deploy.get("next_steps", []),
  }


@router.api_route("/dashboard", methods=["GET", "HEAD"], include_in_schema=False)
async def redirect_dashboard():
  """Redirect browsers to the recommended CRM dashboard."""
  url = await resolve_crm_dashboard_url()
  return RedirectResponse(url=url, status_code=302)


@router.get("/portfolios")
async def get_portfolios(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
  result = await db.execute(select(Portfolio))
  portfolios = result.scalars().all()
  return [
    {
      "bot_type": p.bot_type,
      "balance": p.balance,
      "equity": p.equity,
      "total_pnl": p.total_pnl,
      "win_rate": p.win_rate,
      "total_trades": p.total_trades,
      "winning_trades": p.winning_trades,
      "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
    for p in portfolios
  ]


@router.get("/positions")
async def get_positions(
  bot_type: str | None = None,
  db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
  query = select(Position).where(Position.is_open.is_(True))
  if bot_type:
    query = query.where(Position.bot_type == bot_type)
  result = await db.execute(query)
  positions = result.scalars().all()
  return [
    {
      "id": p.id,
      "bot_type": p.bot_type,
      "symbol": p.symbol,
      "side": p.side,
      "quantity": p.quantity,
      "entry_price": p.entry_price,
      "current_price": p.current_price,
      "unrealized_pnl": p.unrealized_pnl,
      "stop_loss": p.stop_loss,
      "take_profit": p.take_profit,
      "opened_at": p.opened_at.isoformat() if p.opened_at else None,
    }
    for p in positions
  ]


@router.get("/trades")
async def get_trades(
  bot_type: str | None = None,
  limit: int = 100,
  db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
  query = select(Trade).order_by(desc(Trade.executed_at)).limit(limit)
  if bot_type:
    query = query.where(Trade.bot_type == bot_type)
  result = await db.execute(query)
  trades = result.scalars().all()
  return [
    {
      "id": t.id,
      "bot_type": t.bot_type,
      "symbol": t.symbol,
      "side": t.side,
      "action": t.action,
      "quantity": t.quantity,
      "price": t.price,
      "pnl": t.pnl,
      "pnl_pct": t.pnl_pct,
      "is_winner": t.is_winner,
      "strategy": t.strategy,
      "signal_score": t.signal_score,
      "sentiment_score": t.sentiment_score,
      "reason": t.reason,
      "executed_at": t.executed_at.isoformat() if t.executed_at else None,
    }
    for t in trades
  ]


@router.get("/equity-history")
async def get_equity_history(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
  """Daily cumulative realized PnL from closed sells during verification."""
  from app.engines.equity_history import build_equity_history

  result = await db.execute(
    select(Trade).where(Trade.action == "sell").order_by(Trade.executed_at)
  )
  return build_equity_history(list(result.scalars().all()))


@router.get("/bots")
async def get_bots(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
  result = await db.execute(select(BotState))
  states = result.scalars().all()
  config_result = await db.execute(select(StrategyConfig))
  strategy_versions = {c.bot_type: c.version for c in config_result.scalars().all()}
  if not states:
    return [
      {
        "bot_type": bt,
        "status": "running",
        "last_action": "Initializing...",
        "strategy_version": strategy_versions.get(bt, 1),
      }
      for bt in BOT_TYPES
    ]
  return [
    {
      "bot_type": s.bot_type,
      "status": s.status,
      "last_action": s.last_action,
      "last_scan_at": s.last_scan_at.isoformat() if s.last_scan_at else None,
      "trades_today": s.trades_today,
      "pnl_today": s.pnl_today,
      "strategy_version": strategy_versions.get(s.bot_type, s.current_strategy_version),
    }
    for s in states
  ]


@router.get("/bots/{bot_type}/scan-preview")
async def get_bot_scan_preview(bot_type: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Per-symbol signal preview and entry blockers (CRM diagnostics)."""
  from app.engines.scan_preview import build_scan_preview

  if bot_type not in BOT_TYPES:
    return {"error": f"unknown bot_type: {bot_type}"}
  return await build_scan_preview(db, bot_type)


@router.get("/gate/monday-recovery")
async def get_monday_recovery_summary(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Cross-bot Monday recovery candidates for CRM overview banner."""
  from app.engines.scan_preview import build_monday_recovery_summary

  return await build_monday_recovery_summary(db)


@router.get("/gate/prep-status")
async def get_session_prep_status(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Weekend/session TV prep window status for stocks and commodities."""
  from app.engines.gate_prep_status import build_gate_prep_status

  return await build_gate_prep_status(db)


@router.get("/gate/cme-reopen-checklist")
async def get_cme_reopen_checklist(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """CME Sunday reopen preflight and post-open verification checklist."""
  from app.engines.cme_reopen_checklist import build_cme_reopen_checklist

  return await build_cme_reopen_checklist(db)


@router.get("/gate/us-stocks-open-checklist")
async def get_us_stocks_open_checklist(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Monday US stocks open preflight and post-open verification checklist."""
  from app.engines.us_stocks_open_checklist import build_us_stocks_open_checklist

  return await build_us_stocks_open_checklist(db)


@router.get("/intelligence")
async def get_intelligence(
  limit: int = 50,
  category: str | None = None,
  db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
  query = select(IntelligenceItem).order_by(desc(IntelligenceItem.fetched_at)).limit(limit)
  if category:
    query = query.where(IntelligenceItem.category == category)
  result = await db.execute(query)
  items = result.scalars().all()
  return [
    {
      "id": i.id,
      "source": i.source,
      "category": i.category,
      "title": i.title,
      "content": i.content[:300],
      "url": i.url,
      "sentiment": i.sentiment,
      "relevance_score": i.relevance_score,
      "symbols_mentioned": i.symbols_mentioned,
      "fetched_at": i.fetched_at.isoformat() if i.fetched_at else None,
    }
    for i in items
  ]


@router.get("/analyses")
async def get_analyses(
  limit: int = 50,
  db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
  result = await db.execute(
    select(TradeAnalysis).order_by(desc(TradeAnalysis.analyzed_at)).limit(limit)
  )
  analyses = result.scalars().all()
  return [
    {
      "id": a.id,
      "trade_id": a.trade_id,
      "bot_type": a.bot_type,
      "symbol": a.symbol,
      "loss_amount": a.loss_amount,
      "root_cause": a.root_cause,
      "market_context": a.market_context,
      "lessons_learned": a.lessons_learned,
      "strategy_adjustment": a.strategy_adjustment,
      "analyzed_at": a.analyzed_at.isoformat() if a.analyzed_at else None,
    }
    for a in analyses
  ]


@router.get("/reviews")
async def get_reviews(
  limit: int = 30,
  db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
  result = await db.execute(
    select(DailyReview).order_by(desc(DailyReview.created_at)).limit(limit)
  )
  reviews = result.scalars().all()
  return [
    {
      "id": r.id,
      "bot_type": r.bot_type,
      "review_date": r.review_date,
      "total_trades": r.total_trades,
      "losing_trades": r.losing_trades,
      "total_loss": r.total_loss,
      "total_profit": r.total_profit,
      "net_pnl": r.net_pnl,
      "win_rate": r.win_rate,
      "patterns_found": r.patterns_found,
      "conclusions": r.conclusions,
      "strategy_changes": r.strategy_changes,
      "created_at": r.created_at.isoformat() if r.created_at else None,
    }
    for r in reviews
  ]


@router.get("/insights")
async def get_insights(
  limit: int = 50,
  db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
  result = await db.execute(
    select(LearningInsight).order_by(desc(LearningInsight.created_at)).limit(limit)
  )
  insights = result.scalars().all()
  return [serialize_learning_insight(i) for i in insights]


@router.post("/learning/apply-pending-insights")
async def apply_pending_learning_insights(
  db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
  """Apply stored content-study insights to strategy configs (idempotent)."""
  from app.engines.learning_engine import LEARNING_NOISE_DISMISS_MAX_CONFIDENCE, LearningEngine
  from app.ws_manager import push_live_update

  learner = LearningEngine(db)
  applied = await learner.apply_pending_insights(min_confidence=0.55)
  dismissed = await learner.dismiss_noise_insights(
    max_confidence=LEARNING_NOISE_DISMISS_MAX_CONFIDENCE
  )
  await push_live_update()
  return {
    "status": "ok",
    "pending_insights_applied": applied,
    "noise_insights_dismissed": dismissed,
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.get("/strategies")
async def get_strategies(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
  from app.engines.intel_source_status import serialize_strategy_config

  result = await db.execute(select(StrategyConfig))
  configs = result.scalars().all()
  return [serialize_strategy_config(c) for c in configs]


@router.get("/profitability")
async def get_profitability(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  gate = ProfitabilityGate(db)
  result = await gate.evaluate()
  result["per_bot"] = await gate.evaluate_per_bot()
  return result


@router.get("/gate/per-bot")
async def get_per_bot_gate(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Per-bot gate metrics since verification_started_at — includes graduation readiness."""
  gate = ProfitabilityGate(db)
  per_bot = await gate.evaluate_per_bot()
  return {"bots": per_bot, "timestamp": datetime.utcnow().isoformat()}


@router.get("/active-gate")
async def get_active_gate(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Active-bot profitability gate — same shape as dashboard /api/active-gate."""
  gate = ProfitabilityGate(db)
  status = await gate.evaluate()
  return {
    "paused_bots": status.get("paused_bots") or [],
    "active_bots": {
      "total_trades": status["total_trades"],
      "win_rate": status["win_rate"],
      "profit_factor": status["profit_factor"],
      "total_pnl": status["total_pnl"],
    },
    "aggregate": status.get("aggregate") or {
      "total_trades": status["total_trades"],
      "win_rate": status["win_rate"],
      "profit_factor": status["profit_factor"],
      "total_pnl": status["total_pnl"],
    },
    "verification_day": status.get("verification_day"),
    "verification_days_remaining": status.get("verification_days_remaining"),
    "live_trading_ready": status.get("live_trading_ready"),
    "checks": status.get("checks"),
    "recommendation": status.get("recommendation"),
    "per_bot": await gate.evaluate_per_bot(),
  }


@router.get("/verification/history")
async def get_verification_history(
  limit: int = 30,
  db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
  result = await db.execute(
    select(VerificationSnapshot)
    .order_by(desc(VerificationSnapshot.snapshot_date))
    .limit(min(limit, 90))
  )
  snapshots = result.scalars().all()
  return [serialize_verification_snapshot(s) for s in snapshots]


@router.get("/intelligence/routing")
async def get_intelligence_routing() -> dict[str, Any]:
  from app.engines.intelligence_scoring import BOT_SOURCE_WEIGHTS
  from app.intelligence.political_signals import POLITICAL_EVENT_PATTERNS

  return {
    "bot_source_weights": BOT_SOURCE_WEIGHTS,
    "political_event_types": [
      {"type": event_type, "assets": assets, "bots": bots}
      for _, event_type, assets, bots in POLITICAL_EVENT_PATTERNS
    ],
  }


@router.get("/intelligence/sources")
async def get_intelligence_sources(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
  from app.engines.intel_source_status import build_intel_sources

  return await build_intel_sources(db)


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  portfolios = (await db.execute(select(Portfolio))).scalars().all()
  trades = (await db.execute(select(Trade).where(Trade.action == "sell"))).scalars().all()
  open_positions = (
    await db.execute(select(func.count(Position.id)).where(Position.is_open.is_(True)))
  ).scalar_one()
  intel_count = (await db.execute(select(func.count(IntelligenceItem.id)))).scalar_one()

  total_equity = sum(p.equity for p in portfolios)
  total_pnl = sum(p.total_pnl for p in portfolios)
  total_trades = sum(p.total_trades for p in portfolios)
  avg_win_rate = aggregate_win_rate(trades)

  return {
    "total_equity": total_equity,
    "total_pnl": total_pnl,
    "total_trades": total_trades,
    "avg_win_rate": avg_win_rate,
    "open_positions": open_positions,
    "intelligence_items": intel_count,
    "mode": "paper_trading",
    "bots_active": len(BOT_TYPES),
  }


@router.get("/status")
async def get_platform_status(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  from app.engines.platform_status import build_platform_status

  return await build_platform_status(db)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
  from app.ws_manager import build_live_payload, manager

  await manager.connect(websocket)
  try:
    while True:
      async with SessionLocal() as db:
        payload = await build_live_payload(db)
      await websocket.send_json(payload)
      await asyncio.sleep(5)
  except WebSocketDisconnect:
    manager.disconnect(websocket)
  except Exception:
    manager.disconnect(websocket)


@router.post("/admin/apply-risk-migrations")
async def apply_risk_migrations(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
  """Apply Polymarket strategy caps and trim oversized positions (requires webhook secret)."""
  from app.engines.gate_entry_guard import sync_gate_bot_pauses, sync_gate_recovery_rotation
  from app.engines.strategy_migration import (
    adapt_for_gate_win_rate,
    clamp_verification_strategy_params,
    ensure_polymarket_strategy,
    fix_breakeven_trade_labels,
    dedupe_polymarket_positions,
    close_excess_commodities_positions,
    close_excess_shadow_positions,
    close_non_macro_polymarket_positions,
    recalculate_portfolio_win_rates,
    reconcile_portfolio_balances,
    sync_bot_strategy_versions,
    trim_oversized_polymarket_positions,
  )

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  gate_paused = await sync_gate_bot_pauses(db)
  gate_rotation = await sync_gate_recovery_rotation(db)
  clamped = await clamp_verification_strategy_params(db)
  gate_adapted = await adapt_for_gate_win_rate(db)
  strategy_updated = await ensure_polymarket_strategy(db)
  reconciled = await reconcile_portfolio_balances(db)
  trimmed = await trim_oversized_polymarket_positions(db)
  synced = await sync_bot_strategy_versions(db)
  breakeven_fixed = await fix_breakeven_trade_labels(db)
  portfolios_updated = await recalculate_portfolio_win_rates(db)
  pm_deduped = await dedupe_polymarket_positions(db)
  pm_sports_closed = await close_non_macro_polymarket_positions(db)
  commodities_trimmed = await close_excess_commodities_positions(db)
  shadow_trimmed = await close_excess_shadow_positions(db)
  return {
    "status": "ok",
    "gate_paused": gate_paused,
    "gate_rotation": gate_rotation,
    "strategies_clamped": clamped,
    "gate_adapted": gate_adapted,
    "strategy_updated": strategy_updated,
    "portfolios_reconciled": reconciled,
    "positions_trimmed": trimmed,
    "bot_versions_synced": synced,
    "breakeven_trades_fixed": breakeven_fixed,
    "portfolios_recalculated": portfolios_updated,
    "polymarket_duplicates_closed": pm_deduped,
    "polymarket_sports_closed": pm_sports_closed,
    "commodities_excess_closed": commodities_trimmed,
    "shadow_excess_closed": shadow_trimmed,
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/run-commodities-prep")
async def run_commodities_prep_admin(payload: dict[str, Any]) -> dict[str, Any]:
  """Refresh TradingView signals for commodities futures within 90 min of CME open."""
  from app.engines.gate_entry_guard import commodities_session_info
  from app.workers.scheduler import commodities_pre_session_prep_job

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  session_info = commodities_session_info()
  await commodities_pre_session_prep_job()
  return {
    "status": "ok",
    "session": session_info,
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/run-stocks-prep")
async def run_stocks_prep_admin(payload: dict[str, Any]) -> dict[str, Any]:
  """Refresh TradingView signals for proven stock winners within prep window (up to 72h when trade-count nudge)."""
  from app.engines.gate_entry_guard import stocks_session_info
  from app.workers.scheduler import stocks_pre_session_prep_job

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  session_info = stocks_session_info()
  await stocks_pre_session_prep_job()
  return {
    "status": "ok",
    "session": session_info,
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/run-daily-review")
async def run_daily_review_admin(payload: dict[str, Any]) -> dict[str, Any]:
  """Upsert today's daily reviews for all bots (requires webhook secret)."""
  from app.workers.scheduler import daily_review_job

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  await daily_review_job()
  return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.post("/admin/run-intelligence-scan")
async def run_intelligence_scan_admin(payload: dict[str, Any]) -> dict[str, Any]:
  """Force immediate intel scan (DexScreener, Hyperliquid, whales, X, Reddit)."""
  from app.workers.scheduler import intelligence_job

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  await intelligence_job()
  return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.post("/admin/run-content-study")
async def run_content_study_admin(payload: dict[str, Any]) -> dict[str, Any]:
  """Run content study and apply pending learning insights (requires webhook secret)."""
  from app.engines.learning_engine import LEARNING_NOISE_DISMISS_MAX_CONFIDENCE, LearningEngine
  from app.workers.scheduler import content_study_job

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  await content_study_job()
  async with SessionLocal() as session:
    learner = LearningEngine(session)
    pending_applied = await learner.apply_pending_insights(
      min_confidence=float(payload.get("min_confidence", 0.55))
    )
    dismissed = await learner.dismiss_noise_insights(
      max_confidence=float(payload.get("dismiss_below", LEARNING_NOISE_DISMISS_MAX_CONFIDENCE))
    )
  return {
    "status": "ok",
    "pending_insights_applied": pending_applied,
    "noise_insights_dismissed": dismissed,
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/set-bot-paused")
async def set_bot_paused_admin(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Pause or resume a bot (requires webhook secret). Pausing PM sets max_position_pct to 0."""
  from app.engines.platform_settings import set_bot_paused
  from app.models.entities import StrategyConfig

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  bot_type = payload.get("bot_type", "")
  if bot_type not in BOT_TYPES:
    return {"status": "error", "message": f"Unknown bot_type: {bot_type}"}

  paused = bool(payload.get("paused", True))
  await set_bot_paused(db, bot_type, paused)

  if bot_type == "polymarket":
    result = await db.execute(select(StrategyConfig).where(StrategyConfig.bot_type == "polymarket"))
    config = result.scalar_one_or_none()
    if config:
      config.max_position_pct = 0.0 if paused else settings.polymarket_max_position_pct
      config.version += 1
      config.updated_at = datetime.utcnow()
      await db.commit()

  return {
    "status": "ok",
    "bot_type": bot_type,
    "paused": paused,
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/sync-gate-pauses")
async def sync_gate_pauses_admin(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Pause chronic underperformers when aggregate gate WR is below target (requires webhook secret)."""
  from app.engines.gate_entry_guard import sync_gate_bot_pauses, sync_gate_recovery_rotation
  from app.engines.profitability_gate import ProfitabilityGate

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  paused = await sync_gate_bot_pauses(db)
  gate_rotation = await sync_gate_recovery_rotation(db)
  gate = await ProfitabilityGate(db).evaluate()
  return {
    "status": "ok",
    "gate_paused": paused,
    "gate_rotation": gate_rotation,
    "win_rate": gate.get("win_rate"),
    "total_trades": gate.get("total_trades"),
    "paused_bots": gate.get("paused_bots"),
    "recommendation": gate.get("recommendation"),
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/trigger-deploy")
async def trigger_deploy_admin(payload: dict[str, Any]) -> dict[str, Any]:
  """Trigger Render redeploy when stale (webhook secret + RENDER_DEPLOY_HOOK env or platform setting)."""
  from app.engines.deploy_trigger import maybe_trigger_stale_redeploy

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  result = await maybe_trigger_stale_redeploy(
    force=bool(payload.get("force")),
    allow_stale_hook=bool(payload.get("allow_stale_hook")),
  )
  return {"status": "ok", **result, "timestamp": datetime.utcnow().isoformat()}


@router.post("/admin/set-deploy-hook")
async def set_deploy_hook_admin(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Store Render deploy hook URL in platform_settings (requires webhook secret)."""
  from app.engines.platform_settings import set_render_deploy_hook

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  hook_url = (payload.get("hook_url") or "").strip()
  if not hook_url.startswith("https://"):
    return {"status": "error", "message": "hook_url must be an https URL"}

  await set_render_deploy_hook(db, hook_url)
  return {
    "status": "ok",
    "hook_configured": True,
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/set-vercel-deploy-hook")
async def set_vercel_deploy_hook_admin(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Store Vercel deploy hook URL in platform_settings (requires webhook secret)."""
  from app.engines.platform_settings import set_vercel_deploy_hook

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  hook_url = (payload.get("hook_url") or "").strip()
  if not hook_url.startswith("https://"):
    return {"status": "error", "message": "hook_url must be an https URL"}

  await set_vercel_deploy_hook(db, hook_url)
  return {
    "status": "ok",
    "hook_configured": True,
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/set-fomo-bearer")
async def set_fomo_bearer_admin(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Store fomo.family session bearer for server-side trade polling."""
  from app.engines.platform_settings import set_fomo_bearer_token

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  bearer = (payload.get("bearer_token") or payload.get("bearer") or "").strip()
  if len(bearer) < 20:
    return {"status": "error", "message": "bearer_token required (from fomo.family DevTools Authorization header)"}

  await set_fomo_bearer_token(db, bearer)
  from app.intelligence.fomo_tracker import decode_bearer_expiry

  expiry = decode_bearer_expiry(bearer) or {}
  return {
    "status": "ok",
    "fomo_bearer_configured": True,
    "poll_endpoint": "prod-api.fomo.family/trades",
    "fomo_bearer_expires_at": expiry.get("expires_at"),
    "fomo_bearer_minutes_remaining": expiry.get("minutes_remaining"),
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/poll-fomo-trades")
async def poll_fomo_trades_admin(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Immediately poll fomo.family trades feed (requires bearer token)."""
  from app.intelligence.fomo_tracker import scan_fomo_trades
  from app.ws_manager import push_live_update

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  ingested = await scan_fomo_trades(db)
  await push_live_update()
  from app.intelligence.fomo_tracker import get_fomo_bearer_status

  bearer_status = await get_fomo_bearer_status(db)
  return {
    "status": "ok",
    "ingested": ingested,
    "fomo_bearer": bearer_status,
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/trigger-vercel-deploy")
async def trigger_vercel_deploy_admin(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Trigger Vercel production deploy via stored deploy hook."""
  import httpx
  from app.engines.platform_settings import get_vercel_deploy_hook

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  hook_url = (payload.get("hook_url") or os.environ.get("VERCEL_DEPLOY_HOOK") or "").strip()
  if not hook_url:
    stored = await get_vercel_deploy_hook(db)
    hook_url = (stored or "").strip()
  if not hook_url:
    return {
      "status": "error",
      "message": "No Vercel deploy hook — set VERCEL_DEPLOY_HOOK or POST /admin/set-vercel-deploy-hook",
    }

  try:
    async with httpx.AsyncClient(timeout=30.0) as client:
      response = await client.post(hook_url)
      response.raise_for_status()
  except Exception as exc:
    return {"status": "error", "message": str(exc), "hook_url_prefix": hook_url[:48] + "..."}

  return {
    "status": "ok",
    "triggered": True,
    "message": "Vercel deploy hook triggered",
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/reset-paper-trading")
async def reset_paper_trading_admin(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
  """Reset paper portfolios to $100k/bot; clears trades/positions/reviews, keeps intel + strategies."""
  from app.engines.paper_reset import reset_paper_trading
  from app.engines.strategy_migration import ensure_polymarket_strategy, sync_bot_strategy_versions

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  result = await reset_paper_trading(db)
  strategy_updated = await ensure_polymarket_strategy(db)
  synced = await sync_bot_strategy_versions(db)
  return {
    "status": "ok",
    **result,
    "strategy_updated": strategy_updated,
    "bot_versions_synced": synced,
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/webhooks/wallet")
async def wallet_webhook(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
  """Ingest whale wallet moves or external social-monitor events into intel pipeline."""
  from app.config import settings
  from app.intelligence.wallet_tracker import ingest_wallet_webhook
  from app.ws_manager import push_live_update

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  result = await ingest_wallet_webhook(db, payload)
  await push_live_update()
  return result


@router.get("/fomo/userscript")
async def fomo_userscript() -> Response:
  """Serve Tampermonkey userscript for fomo.family → Apex webhook bridge."""
  from app.fomo_userscript import load_fomo_userscript_bytes

  try:
    body = load_fomo_userscript_bytes()
  except FileNotFoundError:
    return Response(
      content=b"fomo bridge userscript not found on server",
      status_code=404,
      media_type="text/plain",
    )
  return Response(content=body, media_type="application/javascript")


@router.post("/webhooks/fomo")
async def fomo_webhook(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
  """Ingest fomo.family trader alerts / copy-trade signals into intel pipeline."""
  from app.config import settings
  from app.intelligence.fomo_tracker import ingest_fomo_webhook
  from app.ws_manager import push_live_update

  if not settings.fomo_enabled:
    return {"status": "disabled"}
  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  result = await ingest_fomo_webhook(db, payload)
  await push_live_update()
  return result


@router.get("/axiom/userscript")
async def axiom_userscript() -> Response:
  """Serve Tampermonkey userscript for axiom.trade → Apex webhook bridge."""
  from app.fomo_userscript import load_axiom_userscript_bytes

  try:
    body = load_axiom_userscript_bytes()
  except FileNotFoundError:
    return Response(
      content=b"axiom bridge userscript not found on server",
      status_code=404,
      media_type="text/plain",
    )
  return Response(content=body, media_type="application/javascript")


@router.get("/phantom/userscript")
async def phantom_userscript() -> Response:
  """Serve Tampermonkey userscript for Phantom → Apex webhook bridge."""
  from app.fomo_userscript import load_phantom_userscript_bytes

  try:
    body = load_phantom_userscript_bytes()
  except FileNotFoundError:
    return Response(
      content=b"phantom bridge userscript not found on server",
      status_code=404,
      media_type="text/plain",
    )
  return Response(content=body, media_type="application/javascript")


@router.post("/webhooks/axiom")
async def axiom_webhook(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
  """Ingest axiom.trade multi-wallet trades and alerts into intel pipeline."""
  from app.config import settings
  from app.intelligence.axiom_tracker import ingest_axiom_webhook
  from app.ws_manager import push_live_update

  if not settings.axiom_enabled:
    return {"status": "disabled"}
  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  result = await ingest_axiom_webhook(db, payload)
  await push_live_update()
  return result


@router.post("/webhooks/phantom")
async def phantom_webhook(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
  """Ingest Phantom wallet portfolio / watchlist events into intel pipeline."""
  from app.config import settings
  from app.intelligence.phantom_tracker import ingest_phantom_webhook
  from app.ws_manager import push_live_update

  if not settings.phantom_enabled:
    return {"status": "disabled"}
  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  result = await ingest_phantom_webhook(db, payload)
  await push_live_update()
  return result


@router.post("/admin/set-axiom-session")
async def set_axiom_session_admin(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Store axiom.trade session token for optional server-side feed polling."""
  from app.engines.platform_settings import set_axiom_session_token

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  session_token = (payload.get("session_token") or payload.get("token") or "").strip()
  if len(session_token) < 20:
    return {"status": "error", "message": "session_token required (from axiom.trade DevTools Authorization header)"}

  await set_axiom_session_token(db, session_token)
  from app.intelligence.axiom_tracker import get_axiom_session_status

  status = await get_axiom_session_status(db)
  return {
    "status": "ok",
    "axiom_session_configured": True,
    "axiom_session_polling_active": status.get("polling_active"),
    "multi_wallet_ready": status.get("multi_wallet_ready"),
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/poll-phantom-portfolios")
async def poll_phantom_portfolios_admin(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Immediately poll Phantom-tracked Solana wallets (Helius or RPC fallback)."""
  from app.intelligence.phantom_tracker import (
    phantom_portfolio_poll_active,
    phantom_portfolio_poll_mode,
    scan_phantom_portfolios,
  )
  from app.ws_manager import push_live_update

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  ingested = await scan_phantom_portfolios(db)
  await push_live_update()
  return {
    "status": "ok",
    "ingested": ingested,
    "phantom_portfolio_poll": phantom_portfolio_poll_active(),
    "phantom_portfolio_poll_mode": phantom_portfolio_poll_mode(),
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/poll-axiom-feed")
async def poll_axiom_feed_admin(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Immediately poll axiom.trade feed (requires session token)."""
  from app.intelligence.axiom_tracker import get_axiom_session_status, scan_axiom_feed
  from app.ws_manager import push_live_update

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  ingested = await scan_axiom_feed(db)
  await push_live_update()
  session_status = await get_axiom_session_status(db)
  return {
    "status": "ok",
    "ingested": ingested,
    "axiom_session": session_status,
    "timestamp": datetime.utcnow().isoformat(),
  }


@router.post("/admin/test-axiom-webhook")
async def test_axiom_webhook(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  sample = {
    "secret": settings.tradingview_webhook_secret,
    "event_type": "trade",
    "symbol": payload.get("symbol", "BONK"),
    "action": payload.get("action", "buy"),
    "wallet_label": payload.get("wallet_label", "axiom_smart_wallet"),
    "wallet_address": payload.get("wallet_address", "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9"),
    "chain": "solana",
    "amount_usd": payload.get("amount_usd", 4200),
    "wallets_watching": 8,
    "message": payload.get("message", "Test axiom multi-wallet buy alert"),
  }
  result = await axiom_webhook(sample, db)
  return {
    "status": "ok",
    "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/axiom",
    "sample_payload": {k: v for k, v in sample.items() if k != "secret"},
    "result": result,
  }


@router.post("/admin/test-phantom-webhook")
async def test_phantom_webhook(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  sample = {
    "secret": settings.tradingview_webhook_secret,
    "event_type": "portfolio",
    "symbol": payload.get("symbol", "SOL"),
    "wallet_address": payload.get("wallet_address", "test_phantom_wallet"),
    "chain": "solana",
    "balance_usd": payload.get("balance_usd", 10000),
    "message": payload.get("message", "Test Phantom portfolio snapshot"),
  }
  result = await phantom_webhook(sample, db)
  return {
    "status": "ok",
    "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/phantom",
    "sample_payload": {k: v for k, v in sample.items() if k != "secret"},
    "result": result,
  }


@router.post("/admin/test-fomo-webhook")
async def test_fomo_webhook(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Inject a sample fomo.family leaderboard trader alert to verify webhook pipeline."""
  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  sample = {
    "secret": settings.tradingview_webhook_secret,
    "event_type": "trade",
    "symbol": payload.get("symbol", "WIF"),
    "action": payload.get("action", "buy"),
    "trader_name": payload.get("trader_name", "fomo_top_trader"),
    "trader_rank": payload.get("trader_rank", 3),
    "trader_pnl_pct": payload.get("trader_pnl_pct", 220.0),
    "chain": payload.get("chain", "solana"),
    "amount_usd": payload.get("amount_usd", 5000),
    "message": payload.get("message", "Test fomo leaderboard trader buy alert"),
  }
  result = await fomo_webhook(sample, db)
  return {
    "status": "ok",
    "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/fomo",
    "sample_payload": {k: v for k, v in sample.items() if k != "secret"},
    "result": result,
  }


@router.post("/admin/test-wallet-webhook")
async def test_wallet_webhook(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Inject a sample whale-wallet alert to verify webhook pipeline."""
  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  sample = {
    "secret": settings.tradingview_webhook_secret,
    "symbol": payload.get("symbol", "BTCUSDT"),
    "action": payload.get("action", "buy"),
    "amount_usd": payload.get("amount_usd", 25000),
    "address": payload.get("address", "0xtestwhale"),
    "chain": "ethereum",
    "tx_hash": f"test-{datetime.utcnow().timestamp()}",
    "message": payload.get("message", "Test whale accumulation alert"),
  }
  result = await wallet_webhook(sample, db)
  return {
    "status": "ok",
    "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/wallet",
    "sample_payload": {k: v for k, v in sample.items() if k != "secret"},
    "result": result,
  }


@router.post("/webhooks/tradingview")
async def tradingview_webhook(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
  from app.config import settings
  from app.models.entities import IntelligenceItem

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  symbol = payload.get("symbol", payload.get("ticker", "UNKNOWN"))
  action = payload.get("action", payload.get("strategy", ""))
  message = payload.get("message", f"TradingView alert: {action} {symbol}")

  item = IntelligenceItem(
    source="tradingview",
    category="technical",
    title=f"TradingView: {action} {symbol}",
    content=message,
    sentiment=0.5 if "buy" in str(action).lower() else -0.5 if "sell" in str(action).lower() else 0.0,
    relevance_score=0.9,
    symbols_mentioned=symbol,
  )
  db.add(item)
  await db.commit()
  from app.ws_manager import push_live_update

  await push_live_update()
  return {"status": "received", "symbol": symbol, "action": action}


@router.post("/admin/test-tradingview-webhook")
async def test_tradingview_webhook(payload: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  """Inject a sample TradingView alert to verify webhook pipeline (requires webhook secret)."""
  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  symbol = payload.get("symbol", "BTCUSDT")
  action = payload.get("action", "buy")
  sample = {
    "secret": settings.tradingview_webhook_secret,
    "symbol": symbol,
    "action": action,
    "message": payload.get("message", f"Test alert: {action} {symbol}"),
  }
  result = await tradingview_webhook(sample, db)
  return {
    "status": "ok",
    "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/tradingview",
    "sample_payload": {
      "secret": "<TRADINGVIEW_WEBHOOK_SECRET>",
      "symbol": symbol,
      "action": action,
      "message": sample["message"],
    },
    "result": result,
    "timestamp": datetime.utcnow().isoformat(),
  }
