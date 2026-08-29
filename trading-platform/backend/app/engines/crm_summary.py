"""CRM landing summaries for live gate state."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.config import BOT_TYPES
from app.engines.gate_entry_guard import build_gate_ws_payload
from app.engines.platform_settings import get_paused_bot_types
from app.intelligence.axiom_tracker import axiom_configured, get_axiom_session_status
from app.intelligence.fomo_tracker import fomo_configured, get_fomo_bearer_status
from app.intelligence.phantom_tracker import (
  parse_phantom_wallet_addresses,
  phantom_configured,
  phantom_poll_wallet_addresses,
  phantom_portfolio_poll_active,
  phantom_portfolio_poll_mode,
)
from app.intelligence.wallet_tracker import wallet_tracker_configured
from app.models.entities import IntelligenceItem, Position


async def build_crm_integration_hooks(session: AsyncSession) -> dict[str, Any]:
  """TradingView and Polymarket hook status for /crm."""
  tv_count = int(
    await session.scalar(
      select(func.count(IntelligenceItem.id)).where(IntelligenceItem.source == "tradingview")
    )
    or 0
  )
  pm_account_count = int(
    await session.scalar(
      select(func.count(IntelligenceItem.id)).where(
        IntelligenceItem.source == "polymarket_account"
      )
    )
    or 0
  )
  pm_intel_count = int(
    await session.scalar(
      select(func.count(IntelligenceItem.id)).where(IntelligenceItem.source == "polymarket")
    )
    or 0
  )

  tv_configured = bool(settings.tradingview_webhook_secret)
  pm_wallet = bool(settings.polymarket_wallet_address or settings.polymarket_deposit_address)
  pm_api = bool(settings.polymarket_api_key)
  fomo_bearer = await get_fomo_bearer_status(session)
  axiom_session = await get_axiom_session_status(session)

  return {
    "tradingview": {
      "configured": tv_configured,
      "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/tradingview",
      "items": tv_count,
    },
    "polymarket": {
      "api_configured": pm_api,
      "wallet_configured": pm_wallet,
      "profile_url": settings.polymarket_profile_url or None,
      "intel_items": pm_intel_count,
      "account_items": pm_account_count,
    },
    "wallet_tracker": {
      "configured": wallet_tracker_configured() or tv_configured,
      "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/wallet",
    },
    "fomo": {
      "configured": fomo_configured(),
      "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/fomo",
      "userscript_url": "https://apex-trading-backend.onrender.com/api/fomo/userscript",
      "bridge_guide": "trading-platform/scripts/fomo-zapier-setup.md",
      "bearer_configured": bool(fomo_bearer.get("configured")),
      "bearer_polling_active": bool(fomo_bearer.get("polling_active")),
      "bearer_expires_at": fomo_bearer.get("expires_at"),
      "bearer_minutes_remaining": fomo_bearer.get("minutes_remaining"),
    },
    "axiom": {
      "configured": axiom_configured(),
      "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/axiom",
      "userscript_url": "https://apex-trading-backend.onrender.com/api/axiom/userscript",
      "session_configured": bool(axiom_session.get("configured")),
      "session_polling_active": bool(axiom_session.get("polling_active")),
      "poll_mode": axiom_session.get("poll_mode"),
      "multi_wallet_ready": bool(axiom_session.get("multi_wallet_ready")),
      "tracked_wallets": axiom_session.get("tracked_wallets"),
      "min_wallets_required": settings.wallet_tracker_min_wallets,
    },
    "phantom": {
      "configured": phantom_configured(),
      "webhook_url": "https://apex-trading-backend.onrender.com/api/webhooks/phantom",
      "userscript_url": "https://apex-trading-backend.onrender.com/api/phantom/userscript",
      "portfolio_poll": phantom_portfolio_poll_active(),
      "portfolio_poll_mode": phantom_portfolio_poll_mode(),
      "tracked_wallets": len(phantom_poll_wallet_addresses()),
      "using_default_wallets": not bool(parse_phantom_wallet_addresses()),
      "note": "Phantom MCP in Cursor is docs-only — webhook, userscript, or Helius portfolio poll",
    },
  }


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
