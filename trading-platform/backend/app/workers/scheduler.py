import asyncio
import os
import time
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bots.trading_bots import CommoditiesBot, CryptoBot, PolymarketBot, StocksFuturesBot
from app.config import BOT_TYPES
from app.database import SessionLocal, init_db
from app.intelligence.content_study import ContentStudyEngine
from app.intelligence.extended_scanners import ExtendedIntelligenceScanner
from app.engines.learning_engine import LEARNING_NOISE_DISMISS_MAX_CONFIDENCE, LearningEngine

scheduler = AsyncIOScheduler()
bots: dict[str, object] = {}
bot_tasks: list[asyncio.Task] = []


async def intelligence_job() -> None:
  count = 0
  async with SessionLocal() as session:
    scanner = ExtendedIntelligenceScanner(session)
    count = await scanner.scan_all()
    print(f"[Intelligence] Scanned {count} new items at {datetime.utcnow().isoformat()}")
  if count > 0:
    from app.ws_manager import push_live_update

    await push_live_update()


async def content_study_job() -> None:
  applied = 0
  intel_applied = 0
  pending_applied = 0
  dismissed = 0
  async with SessionLocal() as session:
    engine = ContentStudyEngine(session)
    applied = await engine.study_and_apply()
    intel_applied = await engine.study_from_intelligence()
    learner = LearningEngine(session)
    dismissed = await learner.dismiss_noise_insights(
      max_confidence=LEARNING_NOISE_DISMISS_MAX_CONFIDENCE,
    )
    pending_applied = await learner.apply_pending_insights(min_confidence=0.55)
    print(
      f"[ContentStudy] Applied {applied} knowledge items, {intel_applied} from intelligence, "
      f"{pending_applied} pending insights, dismissed {dismissed} noise"
    )
  if applied or intel_applied or pending_applied or dismissed:
    from app.ws_manager import push_live_update

    await push_live_update()


async def daily_review_job() -> None:
  today = datetime.utcnow().strftime("%Y-%m-%d")
  async with SessionLocal() as session:
    learner = LearningEngine(session)
    for bot_type in BOT_TYPES:
      review = await learner.run_daily_review(bot_type, today)
      print(
        f"[DailyReview] {bot_type}: {review.total_trades} trades, "
        f"win rate {review.win_rate:.1%}, net PnL ${review.net_pnl:.2f}"
      )
  from app.ws_manager import push_live_update

  await push_live_update()


async def daily_review_refresh_job() -> None:
  """Re-upsert today's reviews so intra-day trades appear before 22:00 UTC cron."""
  await daily_review_job()


async def verification_snapshot_job() -> None:
  from app.engines.verification_snapshot import record_verification_snapshot

  async with SessionLocal() as session:
    snapshot = await record_verification_snapshot(session)
    print(
      f"[VerificationSnapshot] day {snapshot.verification_day}: "
      f"{snapshot.total_trades} trades, WR {snapshot.win_rate:.1%}, "
      f"PF {snapshot.profit_factor:.2f}, PnL ${snapshot.total_pnl:.2f}, "
      f"perf_ok={snapshot.performance_checks_passed}"
    )
  from app.ws_manager import push_live_update

  await push_live_update()


async def reset_daily_bot_stats_job() -> None:
  from sqlalchemy import update

  from app.models.entities import BotState

  async with SessionLocal() as session:
    await session.execute(
      update(BotState).values(trades_today=0, pnl_today=0.0, updated_at=datetime.utcnow())
    )
    await session.commit()
  print(f"[BotStats] Reset daily counters at {datetime.utcnow().isoformat()}")


async def redeploy_check_job() -> None:
  """Periodic staleness log only — deploy triggers are manual or CI to avoid Render email spam."""
  from app.engines.deploy_trigger import auto_redeploy_enabled, maybe_trigger_stale_redeploy

  if not auto_redeploy_enabled():
    return

  result = await maybe_trigger_stale_redeploy()
  if result.get("triggered"):
    print(f"[Deploy] {result.get('message')}")
  elif result.get("deploy", {}).get("is_stale"):
    reason = result.get("reason", "unknown")
    if reason in ("cooldown", "deploy_in_progress", "recent_deploy_failed"):
      return
    print(f"[Deploy] Stale ({reason}) — use Render Manual Deploy or workflow_dispatch render-hook-recovery")


async def stocks_pre_session_prep_job() -> None:
  """90 min before US cash open: refresh TradingView boosts for winners and recovery symbols."""
  from app.engines.gate_entry_guard import (
    get_chronic_loser_symbols,
    get_proven_winner_symbols,
    prioritize_stocks_monday_scan,
    stocks_pre_session_prep_window_minutes,
    stocks_session_info,
    stocks_trade_count_graduation_nudge,
  )
  from app.engines.integration_signals import refresh_tradingview_signals
  from app.engines.platform_settings import is_bot_paused
  from app.engines.profitability_gate import ProfitabilityGate

  session_info = stocks_session_info()
  if session_info["in_session"]:
    return

  minutes_until_open = session_info.get("minutes_until_open")
  if minutes_until_open is None:
    return

  async with SessionLocal() as session:
    shadow_mode = await is_bot_paused(session, "stocks_futures")
    per_bot = (await ProfitabilityGate(session).evaluate_per_bot()).get("stocks_futures") or {}
    trade_count_nudge = stocks_trade_count_graduation_nudge(
      "stocks_futures",
      shadow_mode,
      per_bot.get("win_rate"),
      int(per_bot.get("total_trades") or 0),
    )
    prep_window = stocks_pre_session_prep_window_minutes(trade_count_nudge)
    if minutes_until_open > prep_window:
      return

    winners = await get_proven_winner_symbols(session, "stocks_futures")
    chronic = await get_chronic_loser_symbols(session, "stocks_futures")
    base_symbols = sorted(set(winners) | set(chronic) | {"NVDA"})
    symbols = prioritize_stocks_monday_scan(
      base_symbols,
      chronic_losers=chronic,
      proven_winners=winners,
      session_info=session_info,
      trade_count_nudge=trade_count_nudge,
    )
    refreshed = await refresh_tradingview_signals(
      session,
      symbols,
      reason_prefix="Pre-US-session TV refresh",
      force_refresh=trade_count_nudge,
    )
  if refreshed:
    print(
      f"[StocksPrep] Refreshed TradingView signals for {', '.join(refreshed)} "
      f"({minutes_until_open} min until open)"
    )
    from app.ws_manager import push_live_update

    await push_live_update()


HELD_TV_REFRESH_MAX_AGE_HOURS = 6


async def held_positions_tv_refresh_job() -> None:
  """Refresh stale TradingView boosts for symbols in open active-gate positions."""
  from app.engines.integration_signals import refresh_tradingview_signals
  from app.engines.paper_trading import PaperTradingEngine
  from app.engines.platform_settings import get_paused_bot_types

  async with SessionLocal() as session:
    paused = set(await get_paused_bot_types(session))
    active_bots = [bot_type for bot_type in BOT_TYPES if bot_type not in paused]
    symbols: set[str] = set()
    for bot_type in active_bots:
      engine = PaperTradingEngine(session, bot_type)
      for position in await engine.get_open_positions():
        if position.symbol:
          symbols.add(position.symbol)
    if not symbols:
      return
    refreshed = await refresh_tradingview_signals(
      session,
      sorted(symbols),
      reason_prefix="Held-position TV refresh",
      max_age_hours=HELD_TV_REFRESH_MAX_AGE_HOURS,
    )
  if refreshed:
    print(f"[HeldTVRefresh] Refreshed TradingView signals for {', '.join(refreshed)}")
    from app.ws_manager import push_live_update

    await push_live_update()


COMMODITIES_PREP_SYMBOLS = ("CL=F", "SI=F", "NG=F", "GC=F", "HG=F")


async def commodities_pre_session_prep_job() -> None:
  """90 min before CME futures reopen: refresh TradingView boosts for key commodities."""
  from app.engines.gate_entry_guard import (
    commodities_pre_session_prep_window_minutes,
    commodities_session_info,
    get_chronic_loser_symbols,
    get_proven_winner_symbols,
    in_shadow_graduation_nudge,
    is_commodities_futures_symbol,
    prioritize_commodities_monday_scan,
  )
  from app.engines.integration_signals import refresh_tradingview_signals
  from app.engines.profitability_gate import ProfitabilityGate

  session_info = commodities_session_info()
  if session_info["in_session"]:
    return

  minutes_until_open = session_info.get("minutes_until_open")
  if minutes_until_open is None:
    return

  async with SessionLocal() as session:
    per_bot = (await ProfitabilityGate(session).evaluate_per_bot()).get("commodities") or {}
    bot_wr = per_bot.get("win_rate")
    graduation_nudge = in_shadow_graduation_nudge(
      "commodities",
      bot_wr,
      profit_factor=per_bot.get("profit_factor"),
      total_pnl=per_bot.get("total_pnl"),
    )
    prep_window = commodities_pre_session_prep_window_minutes(graduation_nudge)
    if minutes_until_open > prep_window:
      return

    winners = await get_proven_winner_symbols(session, "commodities")
    chronic = await get_chronic_loser_symbols(session, "commodities")
    recovery_futures = sorted(s for s in chronic if is_commodities_futures_symbol(s))
    base_symbols = sorted(set(COMMODITIES_PREP_SYMBOLS) | set(winners) | set(recovery_futures))
    symbols = prioritize_commodities_monday_scan(
      base_symbols,
      chronic_losers=chronic,
      proven_winners=winners,
      session_info=session_info,
      graduation_nudge=graduation_nudge,
    )
    refreshed = await refresh_tradingview_signals(
      session,
      symbols,
      reason_prefix="Pre-CME-session TV refresh",
      force_refresh=graduation_nudge,
    )
  if refreshed:
    print(
      f"[CommoditiesPrep] Refreshed TradingView signals for {', '.join(refreshed)} "
      f"({minutes_until_open} min until CME open)"
    )
    from app.ws_manager import push_live_update

    await push_live_update()


async def session_prep_phase_monitor_job() -> None:
  """Log CME/US prep phase transitions (extended → imminent → wake → open)."""
  from app.engines.session_open_log import monitor_session_prep_transitions

  async with SessionLocal() as session:
    logged = await monitor_session_prep_transitions(session)
  if logged:
    print(f"[SessionPrepPhase] logged {len(logged)} transition(s)")
    from app.ws_manager import push_live_update

    await push_live_update()


async def session_prep_queue_monitor_job() -> None:
  """Log open-ready and near-floor queue changes from scan preview."""
  from app.engines.gate_entry_guard import commodities_futures_weekend_closed
  from app.engines.session_open_log import (
    backfill_open_ready_queue_events,
    monitor_open_ready_queue,
  )

  if not commodities_futures_weekend_closed():
    return

  async with SessionLocal() as session:
    logged = await monitor_open_ready_queue(session)
    backfilled = await backfill_open_ready_queue_events(session)
  if logged or backfilled:
    total = len(logged) + len(backfilled)
    print(f"[SessionPrepQueue] logged {total} queue event(s)")
    from app.ws_manager import push_live_update

    await push_live_update()


_fomo_bearer_was_polling: bool | None = None


async def fomo_bearer_monitor_job() -> None:
  """Push CRM updates when fomo.family bearer expires or is restored."""
  global _fomo_bearer_was_polling
  from app.intelligence.fomo_tracker import get_fomo_bearer_status

  async with SessionLocal() as session:
    status = await get_fomo_bearer_status(session)
  if not status.get("configured"):
    return
  polling = bool(status.get("polling_active"))
  if _fomo_bearer_was_polling is not None and polling != _fomo_bearer_was_polling:
    state = "restored" if polling else "expired"
    print(f"[FomoBearer] bearer {state} — memecoin polling {'active' if polling else 'paused'}")
    from app.ws_manager import push_live_update

    await push_live_update()
  _fomo_bearer_was_polling = polling


_cme_deploy_reminder_last_at: float = 0.0
CME_DEPLOY_REMINDER_INTERVAL_SECONDS = 1800


def _resolve_cme_deploy_reminder():
  from app.engines.deploy_status import resolve_cme_deploy_reminder

  return resolve_cme_deploy_reminder()


async def _push_cme_deploy_live_update() -> None:
  from app.ws_manager import push_live_update

  await push_live_update()


async def cme_deploy_reminder_job() -> None:
  """Log and push CRM when Render revision is behind and CME reopen is within 6h."""
  global _cme_deploy_reminder_last_at

  urgency = _resolve_cme_deploy_reminder()
  if not urgency:
    if not os.environ.get("PLATFORM_REVISION"):
      _cme_deploy_reminder_last_at = 0.0
    return

  now = time.monotonic()
  if now - _cme_deploy_reminder_last_at < CME_DEPLOY_REMINDER_INTERVAL_SECONDS:
    return

  _cme_deploy_reminder_last_at = now
  from app.engines.deploy_status import EXPECTED_PLATFORM_REVISION

  platform_revision = os.environ.get("PLATFORM_REVISION", "").strip() or "?"
  print(
    f"[CmeDeploy] {urgency['message']} — running {platform_revision}, "
    f"expected {EXPECTED_PLATFORM_REVISION}"
  )
  await _push_cme_deploy_live_update()


async def commodities_cme_reopen_wake_job() -> None:
  """Force-refresh TV signals right before/after CME reopen so open-ready futures enter fast."""
  from app.engines.gate_entry_guard import (
    commodities_reopen_wake_active,
    commodities_session_info,
    get_chronic_loser_symbols,
    get_proven_winner_symbols,
    in_shadow_graduation_nudge,
    prioritize_commodities_monday_scan,
  )
  from app.engines.integration_signals import refresh_tradingview_signals
  from app.engines.profitability_gate import ProfitabilityGate

  session_info = commodities_session_info()
  if not commodities_reopen_wake_active(session_info):
    return

  minutes_until_open = session_info.get("minutes_until_open")
  minutes_since_open = session_info.get("minutes_since_open")
  in_session = bool(session_info.get("in_session"))

  async with SessionLocal() as session:
    per_bot = (await ProfitabilityGate(session).evaluate_per_bot()).get("commodities") or {}
    graduation_nudge = in_shadow_graduation_nudge(
      "commodities",
      per_bot.get("win_rate"),
      profit_factor=per_bot.get("profit_factor"),
      total_pnl=per_bot.get("total_pnl"),
    )
    if not graduation_nudge:
      return

    winners = await get_proven_winner_symbols(session, "commodities")
    chronic = await get_chronic_loser_symbols(session, "commodities")
    symbols = prioritize_commodities_monday_scan(
      list(COMMODITIES_PREP_SYMBOLS),
      chronic_losers=chronic,
      proven_winners=winners,
      session_info=session_info,
      graduation_nudge=True,
    )
    refreshed = await refresh_tradingview_signals(
      session,
      symbols,
      reason_prefix="CME reopen wake TV refresh",
      force_refresh=True,
    )
  if refreshed:
    label = "pre-open" if not in_session else "post-open"
    print(
      f"[CommoditiesReopenWake] {label}: refreshed {', '.join(refreshed)} "
      f"(until_open={minutes_until_open}, since_open={minutes_since_open})"
    )
    from app.ws_manager import push_live_update

    await push_live_update()


async def stocks_us_open_wake_job() -> None:
  """Force-refresh TV signals right before/after US cash open for proven shadow winners."""
  from app.engines.gate_entry_guard import (
    get_chronic_loser_symbols,
    get_proven_winner_symbols,
    prioritize_stocks_monday_scan,
    stocks_open_wake_active,
    stocks_session_info,
    stocks_trade_count_graduation_nudge,
  )
  from app.engines.integration_signals import refresh_tradingview_signals
  from app.engines.platform_settings import is_bot_paused
  from app.engines.profitability_gate import ProfitabilityGate

  session_info = stocks_session_info()
  if not stocks_open_wake_active(session_info):
    return

  minutes_until_open = session_info.get("minutes_until_open")
  minutes_since_open = session_info.get("minutes_since_open")
  in_session = bool(session_info.get("in_session"))

  async with SessionLocal() as session:
    shadow_mode = await is_bot_paused(session, "stocks_futures")
    per_bot = (await ProfitabilityGate(session).evaluate_per_bot()).get("stocks_futures") or {}
    trade_count_nudge = stocks_trade_count_graduation_nudge(
      "stocks_futures",
      shadow_mode,
      per_bot.get("win_rate"),
      int(per_bot.get("total_trades") or 0),
    )
    if not trade_count_nudge:
      return

    winners = await get_proven_winner_symbols(session, "stocks_futures")
    chronic = await get_chronic_loser_symbols(session, "stocks_futures")
    base_symbols = sorted(set(winners) | set(chronic) | {"NVDA", "AAPL"})
    symbols = prioritize_stocks_monday_scan(
      base_symbols,
      chronic_losers=chronic,
      proven_winners=winners,
      session_info=session_info,
      trade_count_nudge=True,
    )
    refreshed = await refresh_tradingview_signals(
      session,
      symbols,
      reason_prefix="US open wake TV refresh",
      force_refresh=True,
    )
  if refreshed:
    label = "pre-open" if not in_session else "post-open"
    print(
      f"[StocksOpenWake] {label}: refreshed {', '.join(refreshed)} "
      f"(until_open={minutes_until_open}, since_open={minutes_since_open})"
    )
    from app.ws_manager import push_live_update

    await push_live_update()


async def risk_migration_job() -> None:
  async with SessionLocal() as session:
    from app.engines.gate_entry_guard import sync_gate_bot_pauses, sync_gate_recovery_rotation, try_graduate_paused_bots
    from app.engines.strategy_migration import (
      adapt_for_gate_win_rate,
      clamp_verification_strategy_params,
      close_excess_commodities_positions,
      close_excess_shadow_positions,
      ensure_polymarket_strategy,
      sync_bot_strategy_versions,
      trim_oversized_polymarket_positions,
    )

    gate_paused = await sync_gate_bot_pauses(session)
    gate_rotation = await sync_gate_recovery_rotation(session)
    gate_graduated = await try_graduate_paused_bots(session)
    learner = LearningEngine(session)
    dismissed = await learner.dismiss_noise_insights(
      max_confidence=LEARNING_NOISE_DISMISS_MAX_CONFIDENCE,
    )
    clamped = await clamp_verification_strategy_params(session)
    adapted = await adapt_for_gate_win_rate(session)
    migrated = await migrate_symbol_columns(session)
    updated = await ensure_polymarket_strategy(session)
    trimmed = await trim_oversized_polymarket_positions(session)
    commodities_trimmed = await close_excess_commodities_positions(session)
    shadow_trimmed = await close_excess_shadow_positions(session)
    synced = await sync_bot_strategy_versions(session)
    if gate_paused or gate_rotation or gate_graduated or dismissed or clamped or adapted or updated or trimmed or commodities_trimmed or shadow_trimmed or synced:
      print(
        f"[RiskMigration] gate_paused={gate_paused} gate_rotation={gate_rotation} gate_graduated={gate_graduated} "
        f"noise_dismissed={dismissed} clamped={clamped} gate_adapted={adapted} "
        f"strategy_updated={updated} trimmed={trimmed} commodities_trimmed={commodities_trimmed} "
        f"shadow_trimmed={shadow_trimmed} synced={synced} at {datetime.utcnow().isoformat()}"
      )


async def start_bots() -> None:
  global bots, bot_tasks
  bots = {
    "crypto": CryptoBot(),
    "stocks_futures": StocksFuturesBot(),
    "commodities": CommoditiesBot(),
    "polymarket": PolymarketBot(),
  }
  for bot in bots.values():
    task = asyncio.create_task(bot.run_loop())
    bot_tasks.append(task)


def stop_bots() -> None:
  for bot in bots.values():
    bot.stop()
  for task in bot_tasks:
    task.cancel()


async def ensure_daily_review_on_startup() -> None:
  """Backfill today's review after deploy if trades occurred but 22:00 UTC cron hasn't run."""
  from sqlalchemy import func, select

  from app.models.entities import DailyReview, Trade

  today = datetime.utcnow().strftime("%Y-%m-%d")
  day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

  async with SessionLocal() as session:
    review_count = (
      await session.execute(
        select(func.count(DailyReview.id)).where(DailyReview.review_date == today)
      )
    ).scalar_one()
    sells_today = (
      await session.execute(
        select(func.count(Trade.id)).where(
          Trade.action == "sell",
          Trade.executed_at >= day_start,
        )
      )
    ).scalar_one()

  if sells_today > 0 and review_count < len(BOT_TYPES):
    print(f"[DailyReview] Startup backfill — {sells_today} sells today, {review_count} review(s)")
    await daily_review_job()


async def ensure_verification_period_on_startup() -> None:
  """Backfill verification start after deploy if paper state was reset without the setting."""
  from sqlalchemy import func, select

  from app.engines.platform_settings import get_verification_started_at, set_verification_started_at
  from app.models.entities import Trade

  async with SessionLocal() as session:
    if await get_verification_started_at(session):
      return
    closed_trades = (
      await session.execute(select(func.count(Trade.id)).where(Trade.action == "sell"))
    ).scalar_one()
    if closed_trades == 0:
      started = await set_verification_started_at(session)
      print(f"[Verification] Started profitability window at {started.isoformat()}")


async def warm_status_caches_job() -> None:
  """Pre-build expensive /api/status and /api/gate/prep-status caches after deploy."""
  from app.engines.gate_prep_status import build_gate_prep_status
  from app.engines.platform_status import build_platform_status

  async with SessionLocal() as session:
    await build_platform_status(session)
    await build_gate_prep_status(session)
  print("[Startup] Warmed platform status and gate prep caches")


async def refresh_status_caches_job() -> None:
  """Keep status caches warm during CME weekend prep so dashboard polls avoid cold builds."""
  from app.engines.gate_entry_guard import commodities_futures_weekend_closed
  from app.engines.gate_prep_status import (
    build_gate_prep_status,
    gate_prep_status_cache_fresh,
  )
  from app.engines.platform_status import (
    build_platform_status,
    platform_status_cache_fresh,
  )

  if not commodities_futures_weekend_closed():
    return
  if platform_status_cache_fresh(30) and gate_prep_status_cache_fresh(30):
    return

  async with SessionLocal() as session:
    if not platform_status_cache_fresh(30):
      await build_platform_status(session)
    if not gate_prep_status_cache_fresh(30):
      await build_gate_prep_status(session)


async def _deferred_startup_jobs() -> None:
  """Heavy intel/learning jobs — run in background so /api/health is ready quickly on Render."""
  try:
    await intelligence_job()
    await content_study_job()
    async with SessionLocal() as session:
      learner = LearningEngine(session)
      dismissed = await learner.dismiss_noise_insights(
        max_confidence=LEARNING_NOISE_DISMISS_MAX_CONFIDENCE,
      )
      if dismissed:
        print(f"[Learning] Dismissed {dismissed} low-confidence noise insight(s)")
      pending = await learner.apply_pending_insights(min_confidence=0.55)
      if pending:
        print(f"[Learning] Applied {pending} pending insight(s) on startup")
    await ensure_daily_review_on_startup()
    await verification_snapshot_job()
    await stocks_pre_session_prep_job()
    await commodities_pre_session_prep_job()
    async with SessionLocal() as session:
      from app.engines.session_open_log import (
        backfill_open_ready_queue_events,
        monitor_open_ready_queue,
        monitor_session_prep_transitions,
      )

      await monitor_session_prep_transitions(session)
      await monitor_open_ready_queue(session)
      backfilled = await backfill_open_ready_queue_events(session)
      if backfilled:
        print(
          "[SessionPrepQueue] backfilled "
          f"{len(backfilled)} open-ready queue event(s) on startup"
        )
        from app.ws_manager import push_live_update

        await push_live_update()
    await warm_status_caches_job()
  except Exception as exc:
    print(f"[Startup] Deferred jobs error: {exc}")


async def setup_scheduler() -> None:
  await init_db()
  from app.engines.deploy_trigger import auto_redeploy_enabled, maybe_trigger_stale_redeploy

  if auto_redeploy_enabled():
    redeploy = await maybe_trigger_stale_redeploy()
    if redeploy.get("triggered"):
      print(f"[Deploy] {redeploy.get('message')}")
    elif redeploy.get("deploy", {}).get("is_stale"):
      reason = redeploy.get("reason", "unknown")
      if reason not in ("cooldown", "deploy_in_progress", "recent_deploy_failed"):
        print(f"[Deploy] Stale ({reason}) — manual deploy or set RENDER_API_KEY on Render")
  else:
    redeploy = await maybe_trigger_stale_redeploy()
    if redeploy.get("triggered"):
      print(f"[Deploy] Stale API redeploy (DISABLE_AUTO_REDEPLOY bypass): {redeploy.get('message')}")
    elif redeploy.get("deploy", {}).get("is_stale"):
      print("[Deploy] Auto-redeploy disabled (DISABLE_AUTO_REDEPLOY) — stale; set RENDER_API_KEY for API recovery")

  from app.engines.deploy_status import EXPECTED_PLATFORM_REVISION, build_cme_deploy_urgency
  from app.engines.gate_entry_guard import commodities_session_info

  cme_session = commodities_session_info()
  platform_revision = os.environ.get("PLATFORM_REVISION", "").strip() or None
  revision_current = (
    platform_revision == EXPECTED_PLATFORM_REVISION if platform_revision else None
  )
  if revision_current is False:
    mins = cme_session.get("minutes_until_open")
    urgency = build_cme_deploy_urgency(
      platform_revision_current=revision_current,
      cme_minutes_until_open=mins,
      cme_in_session=bool(cme_session.get("in_session")),
    )
    if urgency:
      print(f"[CmeDeploy] STARTUP: {urgency['message']}")
    elif mins is not None:
      print(
        f"[CmeDeploy] STARTUP: revision behind ({platform_revision or '?'} vs "
        f"{EXPECTED_PLATFORM_REVISION}), CME open in {mins}min"
      )

  await ensure_verification_period_on_startup()
  async with SessionLocal() as session:
    from app.engines.gate_entry_guard import sync_gate_bot_pauses, sync_gate_recovery_rotation
    from app.engines.strategy_migration import (
      clamp_verification_strategy_params,
      close_excess_commodities_positions,
      close_excess_shadow_positions,
      ensure_polymarket_strategy,
      fix_breakeven_trade_labels,
      dedupe_polymarket_positions,
      migrate_symbol_columns,
      recalculate_portfolio_win_rates,
      reconcile_portfolio_balances,
      sync_bot_strategy_versions,
      trim_oversized_polymarket_positions,
    )

    if await migrate_symbol_columns(session):
      print("[Strategy] Widened symbol columns to VARCHAR(64) for Polymarket slugs")
    reconciled = await reconcile_portfolio_balances(session)
    if reconciled:
      print(f"[Strategy] Reconciled balance/equity on {reconciled} portfolio(s)")
    breakeven_fixed = await fix_breakeven_trade_labels(session)
    if breakeven_fixed:
      print(f"[Strategy] Relabeled {breakeven_fixed} breakeven trade(s)")
    portfolios_updated = await recalculate_portfolio_win_rates(session)
    if portfolios_updated:
      print(f"[Strategy] Recalculated win rates on {portfolios_updated} portfolio(s)")
    pm_deduped = await dedupe_polymarket_positions(session)
    if pm_deduped:
      print(f"[Strategy] Closed {pm_deduped} duplicate Polymarket position(s)")
    gate_paused = await sync_gate_bot_pauses(session)
    if gate_paused:
      print(f"[Strategy] Gate auto-paused underperformers: {', '.join(gate_paused)}")
    gate_rotation = await sync_gate_recovery_rotation(session)
    if gate_rotation:
      print(
        f"[Strategy] Gate recovery rotation: paused {gate_rotation['paused']}, "
        f"activated {gate_rotation['activated']}"
      )
    clamped = await clamp_verification_strategy_params(session)
    if clamped:
      print(f"[Strategy] Clamped over-tight signal thresholds on {clamped} bot(s)")
    if await ensure_polymarket_strategy(session):
      print("[Strategy] Applied Polymarket risk caps on startup")
    trimmed = await trim_oversized_polymarket_positions(session)
    if trimmed:
      print(f"[Strategy] Trimmed {trimmed} oversized Polymarket position(s)")
    commodities_trimmed = await close_excess_commodities_positions(session)
    if commodities_trimmed:
      print(f"[Strategy] Closed {commodities_trimmed} excess commodities position(s)")
    shadow_trimmed = await close_excess_shadow_positions(session)
    if shadow_trimmed:
      print(f"[Strategy] Closed {shadow_trimmed} excess shadow position(s)")
    synced = await sync_bot_strategy_versions(session)
    if synced:
      print(f"[Strategy] Synced strategy version on {synced} bot(s)")
  scheduler.add_job(intelligence_job, "interval", minutes=5, id="intelligence_scan")
  scheduler.add_job(content_study_job, "interval", hours=1, id="content_study")
  scheduler.add_job(risk_migration_job, "interval", minutes=15, id="risk_migration")
  scheduler.add_job(redeploy_check_job, "interval", hours=6, id="redeploy_check")
  scheduler.add_job(
    stocks_pre_session_prep_job,
    "interval",
    minutes=15,
    id="stocks_pre_session_prep_poll",
  )
  scheduler.add_job(
    stocks_pre_session_prep_job,
    "cron",
    hour=13,
    minute=0,
    day_of_week="mon-fri",
    id="stocks_pre_session_prep",
  )
  scheduler.add_job(
    commodities_pre_session_prep_job,
    "interval",
    minutes=15,
    id="commodities_pre_session_prep_poll",
  )
  scheduler.add_job(
    commodities_pre_session_prep_job,
    "cron",
    hour=22,
    minute=30,
    day_of_week="sun",
    id="commodities_pre_session_prep",
  )
  scheduler.add_job(
    commodities_cme_reopen_wake_job,
    "interval",
    minutes=1,
    id="commodities_cme_reopen_wake",
  )
  scheduler.add_job(
    session_prep_phase_monitor_job,
    "interval",
    minutes=1,
    id="session_prep_phase_monitor",
  )
  scheduler.add_job(
    session_prep_queue_monitor_job,
    "interval",
    minutes=5,
    id="session_prep_queue_monitor",
  )
  scheduler.add_job(
    refresh_status_caches_job,
    "interval",
    seconds=45,
    id="refresh_status_caches",
  )
  scheduler.add_job(
    stocks_us_open_wake_job,
    "interval",
    minutes=1,
    id="stocks_us_open_wake",
  )
  scheduler.add_job(
    stocks_pre_session_prep_job,
    "cron",
    hour=14,
    minute=0,
    day_of_week="sat,sun",
    id="stocks_weekend_prep",
  )
  scheduler.add_job(
    held_positions_tv_refresh_job,
    "interval",
    minutes=30,
    id="held_positions_tv_refresh",
  )
  scheduler.add_job(
    fomo_bearer_monitor_job,
    "interval",
    minutes=15,
    id="fomo_bearer_monitor",
  )
  scheduler.add_job(
    cme_deploy_reminder_job,
    "interval",
    minutes=15,
    id="cme_deploy_reminder",
  )
  scheduler.add_job(daily_review_job, "cron", hour=22, minute=0, id="daily_review")
  scheduler.add_job(daily_review_refresh_job, "interval", hours=4, id="daily_review_refresh")
  scheduler.add_job(verification_snapshot_job, "cron", hour=23, minute=0, id="verification_snapshot")
  scheduler.add_job(reset_daily_bot_stats_job, "cron", hour=0, minute=0, id="reset_daily_stats")
  scheduler.start()
  await start_bots()
  asyncio.create_task(_deferred_startup_jobs())
