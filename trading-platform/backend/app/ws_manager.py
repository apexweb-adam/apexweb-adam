from datetime import datetime

from fastapi import WebSocket


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


async def broadcast_trade(trade: dict) -> None:
  await manager.broadcast({
    "type": "trade",
    "timestamp": datetime.utcnow().isoformat(),
    "trade": trade,
  })


async def broadcast_snapshot(stats: dict, portfolios: list, bots: list) -> None:
  await manager.broadcast({
    "type": "update",
    "timestamp": datetime.utcnow().isoformat(),
    "stats": stats,
    "portfolios": portfolios,
    "bots": bots,
  })


async def push_live_update() -> None:
  """Fetch latest platform state and push to all WebSocket clients."""
  from sqlalchemy import select

  from app.database import SessionLocal
  from app.models.entities import BotState, IntelligenceItem, Portfolio, Position, Trade

  async with SessionLocal() as db:
    portfolios = (await db.execute(select(Portfolio))).scalars().all()
    trades = (await db.execute(select(Trade).where(Trade.action == "sell"))).scalars().all()
    positions = (
      await db.execute(select(Position).where(Position.is_open.is_(True)))
    ).scalars().all()
    intel = (await db.execute(select(IntelligenceItem))).scalars().all()
    states = (await db.execute(select(BotState))).scalars().all()

  total_equity = sum(p.equity for p in portfolios)
  total_pnl = sum(p.total_pnl for p in portfolios)
  total_trades = sum(p.total_trades for p in portfolios)
  avg_win_rate = sum(p.win_rate for p in portfolios) / len(portfolios) if portfolios else 0

  stats = {
    "total_equity": total_equity,
    "total_pnl": total_pnl,
    "total_trades": total_trades,
    "avg_win_rate": avg_win_rate,
    "open_positions": len(positions),
    "intelligence_items": len(intel),
    "mode": "paper_trading",
    "bots_active": 3,
  }
  portfolio_data = [
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
  bots = [
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
  ] if states else []
  await broadcast_snapshot(stats, portfolio_data, bots)
