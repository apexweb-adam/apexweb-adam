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
  async with SessionLocal() as session:
    scanner = ExtendedIntelligenceScanner(session)
    count = await scanner.scan_all()
    print(f"[Intelligence] Scanned {count} new items at {datetime.utcnow().isoformat()}")


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


async def reset_daily_bot_stats_job() -> None:
  from sqlalchemy import update

  from app.models.entities import BotState

  async with SessionLocal() as session:
    await session.execute(
      update(BotState).values(trades_today=0, pnl_today=0.0, updated_at=datetime.utcnow())
    )
    await session.commit()
  print(f"[BotStats] Reset daily counters at {datetime.utcnow().isoformat()}")


async def risk_migration_job() -> None:
  async with SessionLocal() as session:
    from app.engines.strategy_migration import (
      clamp_verification_strategy_params,
      ensure_polymarket_strategy,
      sync_bot_strategy_versions,
      trim_oversized_polymarket_positions,
    )

    clamped = await clamp_verification_strategy_params(session)
    updated = await ensure_polymarket_strategy(session)
    trimmed = await trim_oversized_polymarket_positions(session)
    synced = await sync_bot_strategy_versions(session)
    if clamped or updated or trimmed or synced:
      print(
        f"[RiskMigration] clamped={clamped} strategy_updated={updated} trimmed={trimmed} "
        f"synced={synced} at {datetime.utcnow().isoformat()}"
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
  """Run today's review if missing (e.g. fresh Render deploy before 22:00 UTC cron)."""
  from sqlalchemy import select

  from app.models.entities import DailyReview

  today = datetime.utcnow().strftime("%Y-%m-%d")
  async with SessionLocal() as session:
    existing = await session.execute(
      select(DailyReview.id).where(DailyReview.review_date == today).limit(1)
    )
    if existing.scalar_one_or_none():
      return
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
  await ensure_verification_period_on_startup()
  async with SessionLocal() as session:
    from app.engines.strategy_migration import (
      clamp_verification_strategy_params,
      ensure_polymarket_strategy,
      sync_bot_strategy_versions,
      trim_oversized_polymarket_positions,
    )

    clamped = await clamp_verification_strategy_params(session)
    if clamped:
      print(f"[Strategy] Clamped over-tight signal thresholds on {clamped} bot(s)")
    if await ensure_polymarket_strategy(session):
      print("[Strategy] Applied Polymarket risk caps on startup")
    trimmed = await trim_oversized_polymarket_positions(session)
    if trimmed:
      print(f"[Strategy] Trimmed {trimmed} oversized Polymarket position(s)")
    synced = await sync_bot_strategy_versions(session)
    if synced:
      print(f"[Strategy] Synced strategy version on {synced} bot(s)")
  scheduler.add_job(intelligence_job, "interval", minutes=5, id="intelligence_scan")
  scheduler.add_job(content_study_job, "interval", hours=2, id="content_study")
  scheduler.add_job(risk_migration_job, "interval", minutes=15, id="risk_migration")
  scheduler.add_job(daily_review_job, "cron", hour=22, minute=0, id="daily_review")
  scheduler.add_job(reset_daily_bot_stats_job, "cron", hour=0, minute=0, id="reset_daily_stats")
  scheduler.start()

  await intelligence_job()
  await content_study_job()
  await ensure_daily_review_on_startup()
  await start_bots()
