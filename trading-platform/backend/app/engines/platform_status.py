"""Cached /api/status payload — avoids repeated scan-preview and dashboard probes."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BOT_TYPES, settings
from app.database import is_postgres
from app.engines.deploy_status import build_deploy_status, recommended_dashboard_url
from app.engines.gate_entry_guard import (
  build_gate_ws_payload,
  build_next_session_events,
  build_session_prep_status,
  commodities_session_info,
  stocks_session_info,
)
from app.engines.intel_source_status import build_intel_sources
from app.engines.scan_preview import build_monday_recovery_summary
from app.engines.session_open_log import get_session_open_events
from app.engines.trade_stats import aggregate_win_rate
from app.intelligence.axiom_tracker import get_axiom_session_status
from app.intelligence.fomo_tracker import get_fomo_bearer_status
from app.intelligence.phantom_tracker import (
  phantom_poll_wallet_addresses,
  phantom_portfolio_poll_active,
  phantom_portfolio_poll_mode,
)
from app.intelligence.wallet_tracker import wallet_tracker_configured
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

PLATFORM_STATUS_CACHE_TTL_SECONDS = 45
PLATFORM_STATUS_PREP_CACHE_TTL_SECONDS = 60
_platform_status_cache: dict[str, Any] | None = None
_platform_status_cached_at: float = 0.0


def _platform_status_cache_ttl_seconds() -> int:
  """Longer cache during CME weekend prep when /api/status is polled heavily."""
  from app.engines.gate_entry_guard import commodities_futures_weekend_closed

  if commodities_futures_weekend_closed():
    return PLATFORM_STATUS_PREP_CACHE_TTL_SECONDS
  return PLATFORM_STATUS_CACHE_TTL_SECONDS


def clear_platform_status_cache() -> None:
  global _platform_status_cache, _platform_status_cached_at
  _platform_status_cache = None
  _platform_status_cached_at = 0.0


def platform_status_cache_age_seconds() -> float | None:
  if _platform_status_cache is None:
    return None
  return round(time.monotonic() - _platform_status_cached_at, 1)


def platform_status_cache_fresh(max_age_seconds: float) -> bool:
  age = platform_status_cache_age_seconds()
  return age is not None and age < max_age_seconds


async def build_platform_status(session: AsyncSession) -> dict[str, Any]:
  global _platform_status_cache, _platform_status_cached_at
  now = time.monotonic()
  if (
    _platform_status_cache is not None
    and (now - _platform_status_cached_at) < _platform_status_cache_ttl_seconds()
  ):
    cached = dict(_platform_status_cache)
    cached["timestamp"] = datetime.utcnow().isoformat()
    cached["status_cache_hit"] = True
    cached["status_cache_age_seconds"] = round(now - _platform_status_cached_at, 1)
    return cached

  result = await _build_platform_status_uncached(session)
  _platform_status_cache = result
  _platform_status_cached_at = now
  result["status_cache_hit"] = False
  result["status_cache_age_seconds"] = 0.0
  return result


async def _fetch_bot_states(session: AsyncSession) -> list[dict[str, Any]]:
  result = await session.execute(select(BotState))
  states = result.scalars().all()
  config_result = await session.execute(select(StrategyConfig))
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


async def _fetch_stats(session: AsyncSession) -> dict[str, Any]:
  portfolios = (await session.execute(select(Portfolio))).scalars().all()
  trades = (await session.execute(select(Trade).where(Trade.action == "sell"))).scalars().all()
  open_positions = (
    await session.execute(select(func.count(Position.id)).where(Position.is_open.is_(True)))
  ).scalar_one()
  intel_count = (await session.execute(select(func.count(IntelligenceItem.id)))).scalar_one()

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


async def _fetch_learning_counts(session: AsyncSession) -> dict[str, Any]:
  trade_analyses = (
    await session.execute(select(func.count(TradeAnalysis.id)))
  ).scalar_one()
  daily_reviews = (await session.execute(select(func.count(DailyReview.id)))).scalar_one()
  insights_total = (await session.execute(select(func.count(LearningInsight.id)))).scalar_one()
  insights_applied = (
    await session.execute(
      select(func.count(LearningInsight.id)).where(LearningInsight.applied.is_(True))
    )
  ).scalar_one()
  snapshot_count = (
    await session.execute(select(func.count(VerificationSnapshot.id)))
  ).scalar_one()
  return {
    "trade_analyses": trade_analyses,
    "daily_reviews": daily_reviews,
    "insights_applied": insights_applied,
    "insights_total": insights_total,
    "insights_pending": insights_total - insights_applied,
    "verification_snapshots": snapshot_count,
    "content_study_admin": (
      "POST /api/admin/run-content-study with secret to study content and apply pending insights"
    ),
  }


def _dashboard_url_from_deploy(deploy_info: dict[str, Any]) -> str | None:
  if deploy_info.get("vercel_bundle_stale"):
    return deploy_info.get("verified_dashboard_url") or deploy_info.get("dashboard_url")
  return deploy_info.get("dashboard_url") or deploy_info.get("verified_dashboard_url")


async def _build_platform_status_uncached(session: AsyncSession) -> dict[str, Any]:
  stats = await _fetch_stats(session)
  sources = await build_intel_sources(session)
  bots = await _fetch_bot_states(session)
  learning = await _fetch_learning_counts(session)

  active_sources = sum(1 for s in sources if s["status"] in ("active", "degraded"))
  deploy_info = await build_deploy_status()
  dashboard_url = _dashboard_url_from_deploy(deploy_info)
  if not dashboard_url:
    dashboard_url = await recommended_dashboard_url()

  gate_payload = await build_gate_ws_payload(session)
  profitability = gate_payload.get("profitability_gate") or {}
  monday_recovery = await build_monday_recovery_summary(session)
  cme_sess = commodities_session_info()
  us_sess = stocks_session_info()
  session_prep = build_session_prep_status(
    stocks_session=us_sess,
    commodities_session=cme_sess,
    stocks_trade_count_nudge=bool(monday_recovery.get("stocks_trade_count_nudge")),
    commodities_graduation_nudge=bool(monday_recovery.get("commodities_graduation_nudge")),
    open_ready_rows=monday_recovery.get("open_ready"),
    near_floor_rows=monday_recovery.get("near_floor"),
  )
  next_session_events = build_next_session_events(
    session_prep=session_prep,
    commodities_session=cme_sess,
    stocks_session=us_sess,
  )
  session_open_events = await get_session_open_events(session)
  gate_tightening_data = gate_payload["gate_entry_tightening"]

  fomo_bearer = await get_fomo_bearer_status(session)
  axiom_session = await get_axiom_session_status(session)
  tv_items = next((s["items_collected"] for s in sources if s["source"] == "tradingview"), 0)
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
    "per_bot_gate": gate_payload.get("per_bot_gate"),
    "gate_entry_tightening": gate_tightening_data,
    "bot_sessions": gate_payload.get("bot_sessions"),
    "session_prep": session_prep,
    "open_ready_candidates": session_prep.get("open_ready_candidates") or [],
    "next_session_events": next_session_events,
    "session_open_events": session_open_events,
    "bots": bots,
    "intelligence": {
      "active_sources": active_sources,
      "total_sources": len(sources),
      "sources": sources,
    },
    "learning": learning,
    "integrations": _build_integrations_payload(fomo_bearer, axiom_session, tv_items),
    "scheduler": {
      "intelligence_scan": "every 5 min",
      "content_study": "every 1 hour",
      "risk_migration": "every 15 min",
      "redeploy_check": "every 1 hour",
      "stocks_pre_session_prep": (
        "13:00 UTC Mon-Fri + Sat/Sun 14:00 + every 15 min (72h window when trade-count nudge)"
      ),
      "commodities_pre_session_prep": (
        "22:30 UTC Sun + every 15 min (72h window when graduation nudge)"
      ),
      "held_positions_tv_refresh": "every 30 min for open gate positions",
      "daily_review": "22:00 UTC",
      "daily_review_refresh": "every 4 hours",
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
        "reddit": bool(settings.reddit_client_id and settings.reddit_client_secret),
        "wallet_tracker": wallet_tracker_configured(),
      },
      "render_blueprint": "https://render.com/deploy?repo=https://github.com/apexweb-adam/apexweb-adam",
      "supabase_project": "zzgmovjapeyauvpdpuqe",
      "dashboard_url": deploy_info.get(
        "dashboard_url", "https://apex-trading-dashboard-flame.vercel.app"
      ),
      "recommended_dashboard_url": dashboard_url,
      "verified_dashboard_url": deploy_info.get("verified_dashboard_url"),
      "vercel_bundle_stale": deploy_info.get("vercel_bundle_stale"),
      "vercel_bundle_revision": deploy_info.get("vercel_bundle_revision"),
      "vercel_promote_deployment_id": deploy_info.get("vercel_promote_deployment_id"),
      "vercel_promote_url": deploy_info.get("vercel_promote_url"),
      "production_proxy_operational": deploy_info.get("production_proxy_operational"),
      "verified_bundle_revision": deploy_info.get("verified_bundle_revision"),
      "platform_revision": deploy_info.get("platform_revision") or os.environ.get("PLATFORM_REVISION"),
      "expected_platform_revision": deploy_info.get("expected_platform_revision"),
      "platform_revision_current": deploy_info.get("platform_revision_current"),
      "git_commit": deploy_info.get("git_commit"),
      "git_branch": deploy_info.get("git_branch"),
      "latest_main_commit": deploy_info.get("latest_main_commit"),
      "latest_main_message": deploy_info.get("latest_main_message"),
      "is_stale": deploy_info.get("is_stale"),
      "stale_minutes": deploy_info.get("stale_minutes"),
      "commits_behind": deploy_info.get("commits_behind"),
      "pending_changes": deploy_info.get("pending_changes"),
      "github_verified": deploy_info.get("github_verified"),
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


def _build_integrations_payload(
  fomo_bearer: dict[str, Any],
  axiom_session: dict[str, Any],
  tv_items: int,
) -> dict[str, Any]:
  return {
    "tradingview_webhook": bool(settings.tradingview_webhook_secret),
    "tradingview_webhook_url": (
      "https://apex-trading-backend.onrender.com/api/webhooks/tradingview"
      if settings.tradingview_webhook_secret
      else None
    ),
    "tradingview_items": tv_items,
    "tradingview_setup": (
      "Configure TradingView alerts to POST JSON with secret, symbol, action to webhook URL"
      if settings.tradingview_webhook_secret and tv_items == 0
      else None
    ),
    "tradingview_test_endpoint": (
      "POST /api/admin/test-tradingview-webhook with secret to inject a sample alert"
      if settings.tradingview_webhook_secret
      else None
    ),
    "tradingview_example_payload": (
      {
        "secret": "<TRADINGVIEW_WEBHOOK_SECRET>",
        "symbol": "{{ticker}}",
        "action": "{{strategy.order.action}}",
        "message": "TradingView alert on {{ticker}}",
      }
      if settings.tradingview_webhook_secret
      else None
    ),
    "polymarket_market_scanner": True,
    "polymarket_account_hook": bool(
      settings.polymarket_wallet_address or settings.polymarket_deposit_address
    ),
    "polymarket_api_key": bool(settings.polymarket_api_key),
    "newsapi": bool(settings.newsapi_key),
    "twitter_x": bool(settings.twitter_bearer_token),
    "reddit_oauth": bool(settings.reddit_client_id and settings.reddit_client_secret),
    "wallet_tracker": wallet_tracker_configured(),
    "hyperliquid_enabled": settings.hyperliquid_enabled,
    "hyperliquid_perps": "kPEPE,kBONK,WIF,DOGE,MEME,TRUMP,SOL",
    "wallet_tracker_webhook": bool(settings.tradingview_webhook_secret),
    "wallet_tracker_webhook_url": (
      "https://apex-trading-backend.onrender.com/api/webhooks/wallet"
      if settings.tradingview_webhook_secret
      else None
    ),
    "wallet_tracker_example_payload": (
      {
        "secret": "<TRADINGVIEW_WEBHOOK_SECRET>",
        "symbol": "BTCUSDT",
        "action": "buy",
        "amount_usd": 50000,
        "address": "0x…",
        "chain": "ethereum",
        "tx_hash": "0x…",
      }
      if settings.tradingview_webhook_secret
      else None
    ),
    "fomo_family": settings.fomo_enabled,
    "fomo_webhook": bool(settings.fomo_enabled and settings.tradingview_webhook_secret),
    "fomo_bearer_configured": bool(fomo_bearer.get("configured")),
    "fomo_bearer_polling_active": bool(fomo_bearer.get("polling_active")),
    "fomo_bearer_expires_at": fomo_bearer.get("expires_at"),
    "fomo_bearer_minutes_remaining": fomo_bearer.get("minutes_remaining"),
    "fomo_bearer_refresh_hint": (
      "./trading-platform/scripts/fomo-set-bearer.sh 'eyJ...'"
      if fomo_bearer.get("configured") and not fomo_bearer.get("polling_active")
      else None
    ),
    "fomo_webhook_fallback_active": bool(
      fomo_bearer.get("configured") and not fomo_bearer.get("polling_active")
    ),
    "fomo_webhook_url": (
      "https://apex-trading-backend.onrender.com/api/webhooks/fomo"
      if settings.fomo_enabled and settings.tradingview_webhook_secret
      else None
    ),
    "fomo_userscript_url": (
      "https://apex-trading-backend.onrender.com/api/fomo/userscript"
      if settings.fomo_enabled
      else None
    ),
    "fomo_setup": (
      "3 bridges: (1) Tampermonkey on fomo.family — forwards trades + auto-syncs bearer for server polling, "
      "(2) Zapier email/push → webhook — see scripts/fomo-zapier-setup.md, "
      "(3) curl scripts/fomo-send-alert.sh while tuning traders."
      if settings.fomo_enabled and settings.tradingview_webhook_secret
      else None
    ),
    "fomo_bridge_scripts": {
      "userscript": "trading-platform/scripts/fomo-family-bridge.user.js",
      "zapier_guide": "trading-platform/scripts/fomo-zapier-setup.md",
      "manual_curl": "trading-platform/scripts/fomo-send-alert.sh",
      "test_webhook": "trading-platform/scripts/fomo-test-webhook.sh",
    },
    "fomo_example_payload": (
      {
        "secret": "<TRADINGVIEW_WEBHOOK_SECRET>",
        "event_type": "trade",
        "symbol": "WIF",
        "action": "buy",
        "trader_name": "top_trader",
        "trader_rank": 5,
        "trader_pnl_pct": 180.5,
        "chain": "solana",
        "amount_usd": 2500,
        "message": "fomo leaderboard trader opened WIF",
      }
      if settings.fomo_enabled and settings.tradingview_webhook_secret
      else None
    ),
    "axiom_trade": settings.axiom_enabled,
    "axiom_webhook": bool(settings.axiom_enabled and settings.tradingview_webhook_secret),
    "axiom_session_configured": bool(axiom_session.get("configured")),
    "axiom_session_polling_active": bool(axiom_session.get("polling_active")),
    "axiom_poll_mode": axiom_session.get("poll_mode"),
    "axiom_multi_wallet_ready": bool(axiom_session.get("multi_wallet_ready")),
    "axiom_tracked_wallets": axiom_session.get("tracked_wallets"),
    "axiom_min_wallets": settings.wallet_tracker_min_wallets,
    "axiom_webhook_url": (
      "https://apex-trading-backend.onrender.com/api/webhooks/axiom"
      if settings.axiom_enabled and settings.tradingview_webhook_secret
      else None
    ),
    "axiom_userscript_url": (
      "https://apex-trading-backend.onrender.com/api/axiom/userscript"
      if settings.axiom_enabled
      else None
    ),
    "axiom_setup": (
      "Keep axiom.trade open in Tampermonkey bridge for 24/7 multi-wallet memecoin intel "
      f"(minimum {settings.wallet_tracker_min_wallets} Solana wallets tracked by default)."
      if settings.axiom_enabled and settings.tradingview_webhook_secret
      else None
    ),
    "axiom_example_payload": (
      {
        "secret": "<TRADINGVIEW_WEBHOOK_SECRET>",
        "event_type": "trade",
        "symbol": "BONK",
        "action": "buy",
        "wallet_label": "smart_wallet_1",
        "wallet_address": "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",
        "chain": "solana",
        "amount_usd": 3200,
        "wallets_watching": 8,
        "message": "axiom multi-wallet buy on BONK",
      }
      if settings.axiom_enabled and settings.tradingview_webhook_secret
      else None
    ),
    "phantom_wallet": settings.phantom_enabled,
    "phantom_webhook": bool(settings.phantom_enabled and settings.tradingview_webhook_secret),
    "phantom_webhook_url": (
      "https://apex-trading-backend.onrender.com/api/webhooks/phantom"
      if settings.phantom_enabled and settings.tradingview_webhook_secret
      else None
    ),
    "phantom_userscript_url": (
      "https://apex-trading-backend.onrender.com/api/phantom/userscript"
      if settings.phantom_enabled
      else None
    ),
    "phantom_portfolio_poll": phantom_portfolio_poll_active(),
    "phantom_portfolio_poll_mode": phantom_portfolio_poll_mode(),
    "phantom_tracked_wallets": len(phantom_poll_wallet_addresses()),
    "phantom_setup": (
      "Helius portfolio poll uses PHANTOM_WALLET_ADDRESSES or default 8 Solana whales when unset. "
      "Install Phantom userscript for browser forwarding."
      if settings.phantom_enabled
      else None
    ),
    "phantom_example_payload": (
      {
        "secret": "<TRADINGVIEW_WEBHOOK_SECRET>",
        "event_type": "portfolio",
        "symbol": "SOL",
        "wallet_address": "<your_phantom_solana_address>",
        "chain": "solana",
        "balance_usd": 12500,
        "message": "Phantom portfolio snapshot forwarded to Apex",
      }
      if settings.phantom_enabled and settings.tradingview_webhook_secret
      else None
    ),
  }
