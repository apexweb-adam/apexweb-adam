from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings, BOT_TYPES


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
  """Support Supabase/Postgres URLs from Render env (postgres:// or postgresql://)."""
  if url.startswith("postgres://"):
    return url.replace("postgres://", "postgresql+asyncpg://", 1)
  if url.startswith("postgresql://") and "+asyncpg" not in url:
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)
  return url


def _engine_kwargs(url: str) -> dict:
  normalized = normalize_database_url(url)
  kwargs: dict = {"echo": False}
  if normalized.startswith("postgresql+asyncpg://"):
    kwargs["connect_args"] = {"ssl": "require"}
  return kwargs


_db_url = normalize_database_url(settings.database_url)
engine = create_async_engine(_db_url, **_engine_kwargs(settings.database_url))
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def is_postgres() -> bool:
  return _db_url.startswith("postgresql+asyncpg://")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
  import os

  from sqlalchemy import select

  from app.models.entities import BotState, Portfolio, StrategyConfig

  if not is_postgres():
    os.makedirs("data", exist_ok=True)

  async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)

  async with SessionLocal() as session:
    for bot_type in BOT_TYPES:
      result = await session.execute(select(Portfolio).where(Portfolio.bot_type == bot_type))
      if not result.scalar_one_or_none():
        session.add(Portfolio(bot_type=bot_type))

      result = await session.execute(select(StrategyConfig).where(StrategyConfig.bot_type == bot_type))
      if not result.scalar_one_or_none():
        session.add(StrategyConfig(bot_type=bot_type))

      result = await session.execute(select(BotState).where(BotState.bot_type == bot_type))
      if not result.scalar_one_or_none():
        session.add(BotState(bot_type=bot_type, status="running", last_action="Ready"))

    await session.commit()
