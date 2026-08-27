from datetime import datetime

from fastapi import WebSocket
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BOT_TYPES
from app.database import SessionLocal
from app.engines.trade_stats import aggregate_win_rate
from app.models.entities import BotState, IntelligenceItem, Portfolio, Position, StrategyConfig, Trade


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
    dead: list[WebSocket] = []
    for ws in self.active:
      try:
        await ws.send_json(data)
      except Exception:
        dead.append(ws)
    for ws in dead:
      self.disconnect(ws)


manager = ConnectionManager()


async def build_live_payload(session: AsyncSession) -> dict:
  portfolios = (await session.execute(select(Portfolio))).scalars().all()
  sell_trades = (await session.execute(select(Trade).where(Trade.action == "sell"))).scalars().all()
  positions = (
    await session.execute(select(Position).where(Position.is_open.is_(True)))
  ).scalars().all()
  recent_trades = (
    await session.execute(select(Trade).order_by(desc(Trade.executed_at)).limit(50))
  ).scalars().all()
  intel = (await session.execute(select(IntelligenceItem))).scalars().all()
  recent_intel_rows = (
    await session.execute(
      select(IntelligenceItem).order_by(desc(IntelligenceItem.fetched_at)).limit(10)
    )
  ).scalars().all()
  states = (await session.execute(select(BotState))).scalars().all()
  strategy_versions = {
    c.bot_type: c.version
    for c in (await session.execute(select(StrategyConfig))).scalars().all()
  }

  total_equity = sum(p.equity for p in portfolios)
  total_pnl = sum(p.total_pnl for p in portfolios)
  total_trades = sum(p.total_trades for p in portfolios)
  avg_win_rate = aggregate_win_rate(sell_trades)

  return {
    "type": "update",
    "timestamp": datetime.utcnow().isoformat(),
    "stats": {
      "total_equity": total_equity,
      "total_pnl": total_pnl,
      "total_trades": total_trades,
      "avg_win_rate": avg_win_rate,
      "open_positions": len(positions),
      "intelligence_items": len(intel),
      "mode": "paper_trading",
      "bots_active": len(BOT_TYPES),
    },
    "portfolios": [
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
    ],
    "bots": [
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
    ] if states else [],
    "positions": [
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
    ],
    "trades": [
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
      for t in recent_trades
    ],
    "recent_intel": [
      {
        "id": item.id,
        "source": item.source,
        "category": item.category,
        "title": item.title,
        "sentiment": item.sentiment,
        "relevance_score": item.relevance_score,
        "fetched_at": item.fetched_at.isoformat() if item.fetched_at else None,
      }
      for item in recent_intel_rows
    ],
  }


async def broadcast_trade(trade: dict) -> None:
  await manager.broadcast({
    "type": "trade",
    "timestamp": datetime.utcnow().isoformat(),
    "trade": trade,
  })


async def push_live_update() -> None:
  async with SessionLocal() as db:
    payload = await build_live_payload(db)
  await manager.broadcast(payload)
