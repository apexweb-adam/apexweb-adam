"""CRM landing summaries for live gate state."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BOT_TYPES
from app.engines.gate_entry_guard import build_gate_ws_payload
from app.engines.platform_settings import get_paused_bot_types
from app.models.entities import Position


async def build_crm_live_snapshot(session: AsyncSession) -> dict[str, Any]:
  """Open gate positions and entry-tightening summary for /crm."""
  paused = await get_paused_bot_types(session)
  active_bots = [bot for bot in BOT_TYPES if bot not in paused]

  result = await session.execute(
    select(Position)
    .where(Position.is_open.is_(True))
    .order_by(Position.bot_type, Position.symbol)
  )
  positions = list(result.scalars().all())

  gate_payload = await build_gate_ws_payload(session)
  tightening = gate_payload.get("gate_entry_tightening") or {}

  position_rows: list[dict[str, Any]] = []
  for pos in positions:
    position_rows.append(
      {
        "bot_type": pos.bot_type,
        "symbol": pos.symbol,
        "side": pos.side,
        "entry_price": pos.entry_price,
        "current_price": pos.current_price,
        "unrealized_pnl": pos.unrealized_pnl,
        "is_active_gate": pos.bot_type in active_bots,
      }
    )

  blocked = tightening.get("blocked_new_entries") or []
  chronic = tightening.get("chronic_loser_symbols") or {}
  proven = tightening.get("proven_winner_symbols") or {}

  return {
    "active_bots": active_bots,
    "positions": position_rows,
    "gate_tightening": {
      "active": tightening.get("active"),
      "win_rate": tightening.get("win_rate"),
      "min_sentiment": tightening.get("min_sentiment"),
      "require_macd_bullish": tightening.get("require_macd_bullish"),
      "blocked_new_entries": blocked,
      "max_commodities_open_positions": tightening.get("max_commodities_open_positions"),
    },
    "chronic_loser_symbols": chronic,
    "proven_winner_symbols": proven,
  }
