from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import PlatformSetting

VERIFICATION_STARTED_KEY = "verification_started_at"
BOT_PAUSED_PREFIX = "bot_paused:"


async def is_bot_paused(session: AsyncSession, bot_type: str) -> bool:
  raw = await get_platform_setting(session, f"{BOT_PAUSED_PREFIX}{bot_type}")
  return raw == "true"


async def set_bot_paused(session: AsyncSession, bot_type: str, paused: bool) -> None:
  await set_platform_setting(session, f"{BOT_PAUSED_PREFIX}{bot_type}", "true" if paused else "false")


async def get_platform_setting(session: AsyncSession, key: str) -> str | None:
  result = await session.execute(select(PlatformSetting).where(PlatformSetting.key == key))
  row = result.scalar_one_or_none()
  return row.value if row else None


async def set_platform_setting(session: AsyncSession, key: str, value: str) -> None:
  result = await session.execute(select(PlatformSetting).where(PlatformSetting.key == key))
  row = result.scalar_one_or_none()
  if row:
    row.value = value
    row.updated_at = datetime.utcnow()
  else:
    session.add(PlatformSetting(key=key, value=value))
  await session.commit()


async def get_verification_started_at(session: AsyncSession) -> datetime | None:
  raw = await get_platform_setting(session, VERIFICATION_STARTED_KEY)
  if not raw:
    return None
  try:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
  except ValueError:
    return None


async def set_verification_started_at(session: AsyncSession, when: datetime | None = None) -> datetime:
  ts = when or datetime.utcnow()
  await set_platform_setting(session, VERIFICATION_STARTED_KEY, ts.isoformat())
  return ts
