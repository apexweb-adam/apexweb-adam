import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionLocal, get_db
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
  if not states:
    return [
      {"bot_type": "crypto", "status": "running", "last_action": "Initializing..."},
      {"bot_type": "stocks_futures", "status": "running", "last_action": "Initializing..."},
      {"bot_type": "commodities", "status": "running", "last_action": "Initializing..."},
    ]
  return [
    {
      "bot_type": s.bot_type,
      "status": s.status,
      "last_action": s.last_action,
      "last_scan_at": s.last_scan_at.isoformat() if s.last_scan_at else None,
      "trades_today": s.trades_today,
      "pnl_today": s.pnl_today,
      "strategy_version": s.current_strategy_version,
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
    "polymarket_account": bool(settings.polymarket_wallet_address),
    "political": True,
    "tiktok": True,
    "tradingview": bool(settings.tradingview_webhook_secret),
    "x": bool(settings.twitter_bearer_token),
    "newsapi": bool(settings.newsapi_key),
  }

  return [
    {
      "source": source,
      "status": "active" if configured.get(source, source_counts.get(source, 0) > 0) else "pending",
      "items_collected": source_counts.get(source, 0),
      "last_fetched": source_latest.get(source, datetime.utcnow()).isoformat() if source in source_latest else None,
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
    "bots_active": 3,
  }


class ConnectionManager:
  def __init__(self):
    self.active: list[WebSocket] = []

  async def connect(self, websocket: WebSocket) -> None:
    await websocket.accept()
    self.active.append(websocket)

  def disconnect(self, websocket: WebSocket) -> None:
    if websocket in self.active:
      self.active.remove(websocket)

  async def broadcast(self, data: dict) -> None:
    for ws in self.active:
      try:
        await ws.send_json(data)
      except Exception:
        pass


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
  await manager.connect(websocket)
  try:
    while True:
      async with SessionLocal() as db:
        stats = await get_stats(db)
        portfolios = await get_portfolios(db)
        bots_data = await get_bots(db)
      await websocket.send_json({
        "type": "update",
        "timestamp": datetime.utcnow().isoformat(),
        "stats": stats,
        "portfolios": portfolios,
        "bots": bots_data,
      })
      await asyncio.sleep(2)
  except WebSocketDisconnect:
    manager.disconnect(websocket)
  except Exception:
    manager.disconnect(websocket)


@router.post("/webhooks/tradingview")
async def tradingview_webhook(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
  from app.config import settings
  from app.models.entities import IntelligenceItem

  secret = payload.get("secret", "")
  if settings.tradingview_webhook_secret and secret != settings.tradingview_webhook_secret:
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
  return {"status": "received", "symbol": symbol, "action": action}
