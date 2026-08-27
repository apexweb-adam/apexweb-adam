import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings, BOT_TYPES
from app.database import SessionLocal, get_db, is_postgres
from app.engines.profitability_gate import ProfitabilityGate
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
)

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
  return {"status": "ok", "mode": "paper_trading", "timestamp": datetime.utcnow().isoformat()}


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
  avg_win_rate = (
    sum(p.win_rate for p in portfolios) / len(portfolios) if portfolios else 0
  )

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

  active_sources = sum(1 for s in sources if s["status"] in ("active", "degraded"))
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
      "daily_review": "22:00 UTC",
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
      "dashboard_url": "https://apex-trading-dashboard-flame.vercel.app",
      "next_steps": (
        []
        if is_postgres()
        else [
          "Deploy Render Blueprint from main (render.yaml has no disk — Supabase required)",
          "Set DATABASE_URL to Supabase pooler URI — see SUPABASE_SETUP.md",
          "Paste secrets from scripts/export-render-env.sh into Render Environment",
          "Set Vercel BACKEND_URL + BACKEND_WS_URL to Render service URL",
        ]
      ),
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
    ensure_polymarket_strategy,
    sync_bot_strategy_versions,
    trim_oversized_polymarket_positions,
  )

  secret = payload.get("secret", "")
  if not settings.tradingview_webhook_secret or secret != settings.tradingview_webhook_secret:
    return {"status": "unauthorized"}

  strategy_updated = await ensure_polymarket_strategy(db)
  trimmed = await trim_oversized_polymarket_positions(db)
  synced = await sync_bot_strategy_versions(db)
  return {
    "status": "ok",
    "strategy_updated": strategy_updated,
    "positions_trimmed": trimmed,
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
