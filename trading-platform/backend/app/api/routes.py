import asyncio
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings, BOT_TYPES
from app.database import SessionLocal, get_db, is_postgres
from app.engines.deploy_status import build_deploy_status, recommended_dashboard_url
from app.engines.profitability_gate import ProfitabilityGate
from app.engines.trade_stats import aggregate_win_rate
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


@router.get("/dashboard-url")
async def get_dashboard_url() -> dict[str, Any]:
  """Canonical CRM dashboard URL — verified preview when Vercel production bundle is stale."""
  deploy = await build_deploy_status()
  recommended = deploy.get("dashboard_url") or deploy.get("verified_dashboard_url")
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
    "next_steps": deploy.get("next_steps", []),
  }


@router.api_route("/dashboard", methods=["GET", "HEAD"], include_in_schema=False)
async def redirect_dashboard():
  """Redirect browsers to the recommended CRM dashboard."""
  url = await recommended_dashboard_url()
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
  return [
    {
      "id": i.id,
      "source_type": i.source_type,
      "source_title": i.source_title,
      "source_url": i.source_url,
      "key_takeaways": i.key_takeaways,
      "strategy_impact": i.strategy_impact,
      "confidence": i.confidence,
      "applied": i.applied,
      "created_at": i.created_at.isoformat() if i.created_at else None,
    }
    for i in insights
  ]


@router.get("/strategies")
async def get_strategies(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
  result = await db.execute(select(StrategyConfig))
  configs = result.scalars().all()
  return [
    {
      "bot_type": c.bot_type,
      "rsi_oversold": c.rsi_oversold,
      "rsi_overbought": c.rsi_overbought,
      "min_signal_score": c.min_signal_score,
      "min_sentiment_score": c.min_sentiment_score,
      "stop_loss_pct": c.stop_loss_pct,
      "take_profit_pct": c.take_profit_pct,
      "max_position_pct": c.max_position_pct,
      "momentum_weight": c.momentum_weight,
      "sentiment_weight": c.sentiment_weight,
      "technical_weight": c.technical_weight,
      "version": c.version,
      "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    for c in configs
  ]


@router.get("/profitability")
async def get_profitability(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  gate = ProfitabilityGate(db)
  return await gate.evaluate()


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
  return [
    {
      "snapshot_date": s.snapshot_date,
      "verification_day": s.verification_day,
      "total_trades": s.total_trades,
      "win_rate": s.win_rate,
      "profit_factor": s.profit_factor,
      "total_pnl": s.total_pnl,
      "performance_checks_passed": s.performance_checks_passed,
      "live_trading_ready": s.live_trading_ready,
      "created_at": s.created_at.isoformat() if s.created_at else None,
    }
    for s in snapshots
  ]


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
  result = await db.execute(select(IntelligenceItem.source, IntelligenceItem.fetched_at))
  rows = result.all()
  source_counts: dict[str, int] = {}
  source_latest: dict[str, datetime] = {}
  for source, fetched_at in rows:
    source_counts[source] = source_counts.get(source, 0) + 1
    if source not in source_latest or (fetched_at and fetched_at > source_latest[source]):
      source_latest[source] = fetched_at

  configured = {
    "news": True,
    "reddit": True,
    "youtube": True,
    "polymarket": True,
    "polymarket_account": bool(
      settings.polymarket_wallet_address or settings.polymarket_deposit_address
    ),
    "political": True,
    "tiktok": True,
    "tradingview": bool(settings.tradingview_webhook_secret),
    "x": bool(settings.twitter_bearer_token),
    "newsapi": bool(settings.newsapi_key),
  }

  def _status(source: str) -> str:
    has_items = source_counts.get(source, 0) > 0
    is_configured = configured.get(source, has_items)
    if source == "tradingview" and is_configured:
      return "active"  # push webhook — no poll items until alerts fire
    if is_configured and not has_items and source == "x":
      return "degraded"  # token set but API returned no data (often 402 billing)
    if is_configured or has_items:
      return "active"
    return "pending"

  return [
    {
      "source": source,
      "status": _status(source),
      "items_collected": source_counts.get(source, 0),
      "last_fetched": source_latest.get(source).isoformat() if source in source_latest else None,
    }
    for source in ["news", "reddit", "youtube", "x", "tiktok", "polymarket", "polymarket_account", "political", "tradingview", "newsapi"]
  ]


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  portfolios = (await db.execute(select(Portfolio))).scalars().all()
  trades = (await db.execute(select(Trade).where(Trade.action == "sell"))).scalars().all()
  positions = (
    await db.execute(select(Position).where(Position.is_open.is_(True)))
  ).scalars().all()
  intel = (await db.execute(select(IntelligenceItem))).scalars().all()

  total_equity = sum(p.equity for p in portfolios)
  total_pnl = sum(p.total_pnl for p in portfolios)
  total_trades = sum(p.total_trades for p in portfolios)
  avg_win_rate = aggregate_win_rate(trades)

  return {
    "total_equity": total_equity,
    "total_pnl": total_pnl,
    "total_trades": total_trades,
    "avg_win_rate": avg_win_rate,
    "open_positions": len(positions),
    "intelligence_items": len(intel),
    "mode": "paper_trading",
    "bots_active": len(BOT_TYPES),
  }


@router.get("/status")
async def get_platform_status(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  stats = await get_stats(db)
  profitability = await get_profitability(db)
  sources = await get_intelligence_sources(db)
  bots = await get_bots(db)
  analyses = (
    await db.execute(select(TradeAnalysis))
  ).scalars().all()
  reviews = (
    await db.execute(select(DailyReview))
  ).scalars().all()
  insights = (
    await db.execute(select(LearningInsight))
  ).scalars().all()
  snapshot_count = (
    await db.execute(select(func.count(VerificationSnapshot.id)))
  ).scalar_one()

  active_sources = sum(1 for s in sources if s["status"] in ("active", "degraded"))
  deploy_info = await build_deploy_status()
  base_next_steps = (
    []
    if is_postgres()
    else [
      "Deploy Render Blueprint from main (render.yaml has no disk — Supabase required)",
      "Set DATABASE_URL to Supabase pooler URI — see SUPABASE_SETUP.md",
      "Paste secrets from scripts/export-render-env.sh into Render Environment",
      "Set Vercel BACKEND_URL + BACKEND_WS_URL to Render service URL",
    ]
  )
  return {
    "platform": "Apex Trading Platform",
    "version": "1.0.0",
    "timestamp": datetime.utcnow().isoformat(),
    "paper_trading_only": settings.paper_trading_only,
    "database": {
      "engine": "postgresql" if is_postgres() else "sqlite",
      "persistent": is_postgres(),
    },
    "stats": stats,
    "profitability_gate": profitability,
    "bots": bots,
    "intelligence": {
      "active_sources": active_sources,
      "total_sources": len(sources),
      "sources": sources,
    },
    "learning": {
      "trade_analyses": len(analyses),
      "daily_reviews": len(reviews),
      "insights_applied": sum(1 for i in insights if i.applied),
      "insights_total": len(insights),
      "verification_snapshots": snapshot_count,
    },
    "integrations": {
      "tradingview_webhook": bool(settings.tradingview_webhook_secret),
      "polymarket_market_scanner": True,
      "polymarket_account_hook": bool(
        settings.polymarket_wallet_address or settings.polymarket_deposit_address
      ),
      "polymarket_api_key": bool(settings.polymarket_api_key),
      "newsapi": bool(settings.newsapi_key),
      "twitter_x": bool(settings.twitter_bearer_token),
    },
    "scheduler": {
      "intelligence_scan": "every 5 min",
      "content_study": "every 2 hours",
      "risk_migration": "every 15 min",
      "daily_review": "22:00 UTC",
      "verification_snapshot": "23:00 UTC",
    },
    "deploy": {
      "database_persistent": is_postgres(),
      "intelligence_complete": active_sources >= len(sources),
      "env_configured": {
        "newsapi": bool(settings.newsapi_key),
        "twitter": bool(settings.twitter_bearer_token),
        "tradingview": bool(settings.tradingview_webhook_secret),
        "polymarket_wallet": bool(
          settings.polymarket_wallet_address or settings.polymarket_deposit_address
        ),
        "polymarket_api": bool(settings.polymarket_api_key),
      },
      "render_blueprint": "https://render.com/deploy?repo=https://github.com/apexweb-adam/apexweb-adam",
      "supabase_project": "zzgmovjapeyauvpdpuqe",
      "dashboard_url": deploy_info.get("dashboard_url", "https://apex-trading-dashboard-flame.vercel.app"),
      "verified_dashboard_url": deploy_info.get("verified_dashboard_url"),
      "vercel_bundle_stale": deploy_info.get("vercel_bundle_stale"),
      "vercel_bundle_revision": deploy_info.get("vercel_bundle_revision"),
      "vercel_promote_deployment_id": deploy_info.get("vercel_promote_deployment_id"),
      "vercel_promote_url": deploy_info.get("vercel_promote_url"),
      "git_commit": deploy_info.get("git_commit"),
      "git_branch": deploy_info.get("git_branch"),
      "latest_main_commit": deploy_info.get("latest_main_commit"),
      "latest_main_message": deploy_info.get("latest_main_message"),
      "is_stale": deploy_info.get("is_stale"),
      "stale_minutes": deploy_info.get("stale_minutes"),
      "commits_behind": deploy_info.get("commits_behind"),
      "pending_changes": deploy_info.get("pending_changes"),
      "features": {
        "admin_risk_migrations": True,
        "admin_reset_paper_trading": True,
        "polymarket_position_cap": True,
        "startup_strategy_migration": True,
        "aggregate_win_rate": True,
        "breakeven_trade_handling": True,
        "equity_history": True,
        "active_gate": True,
        "intel_routing": True,
      },
      "next_steps": base_next_steps + deploy_info.get("next_steps", []),
    },
  }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
  from app.ws_manager import build_live_payload, manager

  await manager.connect(websocket)
  try:
    while True:
      async with SessionLocal() as db:
        payload = await build_live_payload(db)
      await websocket.send_json(payload)
      await asyncio.sleep(2)
  except WebSocketDisconnect:
    manager.disconnect(websocket)
  except Exception:
    manager.disconnect(websocket)


@router.post("/admin/apply-risk-migrations")
async def apply_risk_migrations(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
  """Apply Polymarket strategy caps and trim oversized positions (requires webhook secret)."""
  from app.engines.strategy_migration import (
    clamp_verification_strategy_params,
    ensure_polymarket_strategy,
    fix_breakeven_trade_labels,
    dedupe_polymarket_positions,
    recalculate_portfolio_win_rates,
    reconcile_portfolio_balances,
    sync_bot_strategy_versions,
    trim_oversized_polymarket_positions,
  )

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  clamped = await clamp_verification_strategy_params(db)
  strategy_updated = await ensure_polymarket_strategy(db)
  reconciled = await reconcile_portfolio_balances(db)
  trimmed = await trim_oversized_polymarket_positions(db)
  synced = await sync_bot_strategy_versions(db)
  breakeven_fixed = await fix_breakeven_trade_labels(db)
  portfolios_updated = await recalculate_portfolio_win_rates(db)
  pm_deduped = await dedupe_polymarket_positions(db)
  return {
    "status": "ok",
    "strategies_clamped": clamped,
    "strategy_updated": strategy_updated,
    "portfolios_reconciled": reconciled,
    "positions_trimmed": trimmed,
    "bot_versions_synced": synced,
    "breakeven_trades_fixed": breakeven_fixed,
    "portfolios_recalculated": portfolios_updated,
    "polymarket_duplicates_closed": pm_deduped,
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


@router.post("/admin/trigger-deploy")
async def trigger_deploy_admin(payload: dict[str, Any]) -> dict[str, Any]:
  """Trigger Render redeploy when stale (webhook secret + RENDER_DEPLOY_HOOK env or platform setting)."""
  from app.engines.deploy_trigger import maybe_trigger_stale_redeploy

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  result = await maybe_trigger_stale_redeploy()
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
