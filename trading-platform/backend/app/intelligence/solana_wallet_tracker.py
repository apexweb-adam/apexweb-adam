"""Solana SPL transfer scanner for memecoin whale wallets."""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.intelligence.memecoin_whales import DEFAULT_SOLANA_WHALE_ADDRESSES
from app.intelligence.scanner import categorize, extract_symbols, relevance_score
from app.models.entities import IntelligenceItem


def tracked_solana_addresses() -> list[str]:
  custom = [
    a.strip()
    for a in settings.solana_tracker_addresses.split(",")
    if a.strip() and not a.strip().startswith("0x")
  ]
  if custom:
    return custom
  if settings.wallet_tracker_use_defaults:
    return list(DEFAULT_SOLANA_WHALE_ADDRESSES)
  return []


async def scan_solana_wallets(session: AsyncSession) -> int:
  """Poll Helius enhanced transactions for Solana whale wallets."""
  addresses = tracked_solana_addresses()
  if not addresses or not settings.helius_api_key:
    return 0

  count = 0
  base_url = f"https://api.helius.xyz/v0/addresses/{{address}}/transactions"
  params = {"api-key": settings.helius_api_key, "limit": 10}

  async with httpx.AsyncClient(timeout=25) as client:
    for address in addresses:
      try:
        response = await client.get(base_url.format(address=address), params=params)
        if response.status_code != 200:
          continue
        txs = response.json()
        if not isinstance(txs, list):
          continue
        for tx in txs[:8]:
          sig = tx.get("signature", "")
          if not sig:
            continue
          existing = await session.execute(
            select(IntelligenceItem).where(
              IntelligenceItem.source == "wallet_tracker",
              IntelligenceItem.url == sig[:1000],
            )
          )
          if existing.scalar_one_or_none():
            continue

          desc = tx.get("description", "Solana transfer")
          token_transfers = tx.get("tokenTransfers", []) or []
          native = float(tx.get("nativeTransfers", [{}])[0].get("amount", 0) or 0) / 1e9
          usd_est = native * 150
          symbol = "SOLUSDT"
          sentiment = 0.0
          for tt in token_transfers:
            mint = tt.get("mint", "")
            amt = float(tt.get("tokenAmount", 0) or 0)
            if amt * 0.01 > usd_est:
              usd_est = amt * 0.01
            sym = (tt.get("tokenSymbol") or "SPL").upper()
            if sym in ("WIF", "BONK", "PEPE", "DOGE", "TRUMP", "MEME"):
              symbol = f"{sym}USDT"
            to_user = tt.get("toUserAccount", "")
            from_user = tt.get("fromUserAccount", "")
            if to_user == address:
              sentiment = 0.5
            elif from_user == address:
              sentiment = -0.4

          if usd_est < settings.wallet_tracker_min_usd / 2:
            continue

          title = f"[SOL Whale] {desc[:100]} (${usd_est:,.0f})"
          content = (
            f"wallet {address[:8]}… | {desc} | sig {sig[:16]}… | est ${usd_est:,.0f}"
          )
          full_text = f"{title} {content} {symbol}"
          session.add(
            IntelligenceItem(
              source="wallet_tracker",
              category=categorize(full_text) or "crypto",
              title=title[:500],
              content=content[:2000],
              url=sig[:1000],
              sentiment=sentiment or (0.3 if "swap" in desc.lower() else 0.0),
              relevance_score=max(0.7, relevance_score(full_text, "crypto")),
              symbols_mentioned=extract_symbols(full_text) or symbol,
            )
          )
          count += 1
      except Exception as e:
        print(f"Solana wallet scan error for {address[:8]}…: {e}")
  return count
