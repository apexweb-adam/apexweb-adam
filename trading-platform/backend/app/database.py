from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
  import os

  from sqlalchemy import select

  from app.models.entities import BotState, Portfolio, StrategyConfig

  os.makedirs("data", exist_ok=True)
  async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)

  async with SessionLocal() as session:
    for bot_type in ["crypto", "stocks_futures", "commodities"]:
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
