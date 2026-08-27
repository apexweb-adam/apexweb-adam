#!/usr/bin/env python3
"""Reset paper trading state to clean $100k per bot (fixes corrupted P&L from bad prices)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.engines.paper_reset import reset_paper_trading


async def reset() -> None:
  await init_db()
  async with SessionLocal() as session:
    result = await reset_paper_trading(session)
  print(
    f"Paper trading reset complete. Each bot: ${result['initial_balance_per_bot']:,.0f}. "
    f"Intel items kept: {result['intel_items_kept']}"
  )


if __name__ == "__main__":
  asyncio.run(reset())
