from datetime import datetime

from fastapi import WebSocket
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BOT_TYPES
from app.database import SessionLocal
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
  from app.engines.gate_entry_guard import build_gate_ws_payload
  from app.engines.intel_source_status import (
    build_intel_sources,
    serialize_intel_item,
    serialize_strategy_config,
  )
  from app.engines.learning_engine import build_crm_content_study_highlights
  from app.engines.verification_snapshot import serialize_verification_snapshot

  content_study = await build_crm_content_study_highlights(session)
  gate_payload = await build_gate_ws_payload(session)
  from app.engines.scan_preview import build_monday_recovery_summary

  monday_recovery = await build_monday_recovery_summary(session)
  from app.engines.gate_entry_guard import (
    build_session_prep_status,
    build_next_session_events,
    commodities_session_info,
    stocks_session_info,
  )

  cme_session = commodities_session_info()
  stocks_session = stocks_session_info()
  session_prep = build_session_prep_status(
    stocks_session=stocks_session,
    commodities_session=cme_session,
    stocks_trade_count_nudge=bool(monday_recovery.get("stocks_trade_count_nudge")),
    commodities_graduation_nudge=bool(monday_recovery.get("commodities_graduation_nudge")),
    open_ready_rows=monday_recovery.get("open_ready"),
    near_floor_rows=monday_recovery.get("near_floor"),
  )
  next_session_events = build_next_session_events(
    session_prep=session_prep,
    commodities_session=cme_session,
    stocks_session=stocks_session,
  )
  from app.engines.session_open_log import get_session_open_events

  session_open_events = await get_session_open_events(session)
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
      select(IntelligenceItem).order_by(desc(IntelligenceItem.fetched_at)).limit(20)
    )
  ).scalars().all()
  states = (await session.execute(select(BotState))).scalars().all()
  strategy_configs = (await session.execute(select(StrategyConfig))).scalars().all()
  strategy_versions = {c.bot_type: c.version for c in strategy_configs}
  intel_sources = await build_intel_sources(session)
  recent_analyses = (
    await session.execute(select(TradeAnalysis).order_by(desc(TradeAnalysis.analyzed_at)).limit(20))
  ).scalars().all()
  recent_reviews = (
    await session.execute(select(DailyReview).order_by(desc(DailyReview.created_at)).limit(10))
  ).scalars().all()
  recent_insights = (
    await session.execute(select(LearningInsight).order_by(desc(LearningInsight.created_at)).limit(20))
  ).scalars().all()
  verification_history = (
    await session.execute(
      select(VerificationSnapshot).order_by(desc(VerificationSnapshot.snapshot_date)).limit(30)
    )
  ).scalars().all()

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
    "recent_intel": [serialize_intel_item(item) for item in recent_intel_rows],
    "intel_sources": intel_sources,
    "strategies": [serialize_strategy_config(c) for c in strategy_configs],
    "analyses": [
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
      for a in recent_analyses
    ],
    "reviews": [
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
      for r in recent_reviews
    ],
    "insights": [
      {
        "id": i.id,
        "source_type": i.source_type,
        "source_title": i.source_title,
        "source_url": i.source_url,
        "key_takeaways": i.key_takeaways,
        "strategy_impact": i.strategy_impact,
        "confidence": i.confidence,
        "applied": i.applied,
      }
      for i in recent_insights
    ],
    "verification_history": [serialize_verification_snapshot(s) for s in verification_history],
    "monday_recovery": monday_recovery,
    "session_prep": session_prep,
    "next_session_events": next_session_events,
    "session_open_events": session_open_events,
    "content_study": content_study,
    **gate_payload,
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
