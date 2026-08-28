import asyncio
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bots.trading_bots import CommoditiesBot, CryptoBot, PolymarketBot, StocksFuturesBot
from app.config import BOT_TYPES
from app.database import SessionLocal, init_db
from app.intelligence.content_study import ContentStudyEngine
from app.intelligence.extended_scanners import ExtendedIntelligenceScanner
from app.engines.learning_engine import LearningEngine

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
  async with SessionLocal() as session:
    engine = ContentStudyEngine(session)
    applied = await engine.study_and_apply()
    intel_applied = await engine.study_from_intelligence()
    print(f"[ContentStudy] Applied {applied} knowledge items, {intel_applied} from intelligence")


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
  """Hourly: trigger Render redeploy when running build is behind main."""
  from app.engines.deploy_trigger import maybe_trigger_stale_redeploy

  result = await maybe_trigger_stale_redeploy()
  if result.get("triggered"):
    print(f"[Deploy] {result.get('message')}")
  elif result.get("deploy", {}).get("is_stale"):
    reason = result.get("reason", "unknown")
    if reason not in ("cooldown",):
      print(f"[Deploy] Stale ({reason}) — set RENDER_DEPLOY_HOOK on Render or GitHub secrets")


async def risk_migration_job() -> None:
  async with SessionLocal() as session:
    from app.engines.strategy_migration import (
      adapt_for_gate_win_rate,
      clamp_verification_strategy_params,
      close_excess_commodities_positions,
      ensure_polymarket_strategy,
      sync_bot_strategy_versions,
      trim_oversized_polymarket_positions,
    )

    clamped = await clamp_verification_strategy_params(session)
    adapted = await adapt_for_gate_win_rate(session)
    migrated = await migrate_symbol_columns(session)
    updated = await ensure_polymarket_strategy(session)
    trimmed = await trim_oversized_polymarket_positions(session)
    commodities_trimmed = await close_excess_commodities_positions(session)
    synced = await sync_bot_strategy_versions(session)
    if clamped or adapted or updated or trimmed or commodities_trimmed or synced:
      print(
        f"[RiskMigration] clamped={clamped} gate_adapted={adapted} strategy_updated={updated} "
        f"trimmed={trimmed} commodities_trimmed={commodities_trimmed} synced={synced} "
        f"at {datetime.utcnow().isoformat()}"
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


async def setup_scheduler() -> None:
  await init_db()
  from app.engines.deploy_trigger import maybe_trigger_stale_redeploy

  redeploy = await maybe_trigger_stale_redeploy()
  if redeploy.get("triggered"):
    print(f"[Deploy] {redeploy.get('message')}")
  elif redeploy.get("deploy", {}).get("is_stale"):
    print(f"[Deploy] Stale ({redeploy.get('reason')}) — manual deploy or set RENDER_DEPLOY_HOOK on Render")

  await ensure_verification_period_on_startup()
  async with SessionLocal() as session:
    from app.engines.strategy_migration import (
      clamp_verification_strategy_params,
      close_excess_commodities_positions,
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
    synced = await sync_bot_strategy_versions(session)
    if synced:
      print(f"[Strategy] Synced strategy version on {synced} bot(s)")
  scheduler.add_job(intelligence_job, "interval", minutes=5, id="intelligence_scan")
  scheduler.add_job(content_study_job, "interval", hours=2, id="content_study")
  scheduler.add_job(risk_migration_job, "interval", minutes=15, id="risk_migration")
  scheduler.add_job(redeploy_check_job, "interval", hours=1, id="redeploy_check")
  scheduler.add_job(daily_review_job, "cron", hour=22, minute=0, id="daily_review")
  scheduler.add_job(verification_snapshot_job, "cron", hour=23, minute=0, id="verification_snapshot")
  scheduler.add_job(reset_daily_bot_stats_job, "cron", hour=0, minute=0, id="reset_daily_stats")
  scheduler.start()

  await intelligence_job()
  await content_study_job()
  async with SessionLocal() as session:
    learner = LearningEngine(session)
    dismissed = await learner.dismiss_noise_insights(max_confidence=0.5)
    if dismissed:
      print(f"[Learning] Dismissed {dismissed} low-confidence noise insight(s)")
    pending = await learner.apply_pending_insights(min_confidence=0.55)
    if pending:
      print(f"[Learning] Applied {pending} pending insight(s) on startup")
  await ensure_daily_review_on_startup()
  await verification_snapshot_job()
  await start_bots()
