"""Prediction-market signals — momentum + intel, not generic MACD on synthetic OHLCV."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import IntelligenceItem

PM_INTEL_SOURCES = ("polymarket", "polymarket_account", "political", "news", "x")


@dataclass
class PolymarketSignal:
  direction: str
  score: float
  sentiment: float
  reason: str


def _keywords(text: str) -> set[str]:
  stop = {"will", "the", "before", "after", "win", "be", "a", "an", "in", "on", "to", "of", "by", "or", "and"}
  return {w for w in text.lower().replace("-", " ").split() if len(w) > 3 and w not in stop}


async def pm_intel_sentiment(session: AsyncSession, slug: str, question: str) -> float:
  slug_key = slug.replace("-", " ").lower()
  keys = _keywords(f"{slug} {question}")
  cutoff = datetime.utcnow() - timedelta(hours=48)

  result = await session.execute(
    select(IntelligenceItem)
    .where(
      IntelligenceItem.source.in_(PM_INTEL_SOURCES),
      IntelligenceItem.fetched_at >= cutoff,
    )
    .order_by(IntelligenceItem.fetched_at.desc())
    .limit(120)
  )

  scores: list[float] = []
  for item in result.scalars().all():
    hay = f"{item.title} {item.content} {item.url or ''}".lower()
    if slug_key[:20] in hay or any(k in hay for k in keys if len(k) > 4):
      scores.append(item.sentiment * min(1.0, item.relevance_score or 0.5))

  if not scores:
    return 0.0
  return sum(scores) / len(scores)


def _price_momentum(df: pd.DataFrame | None) -> float:
  if df is None or len(df) < 5:
    return 0.0
  close = df["close"] if "close" in df.columns else df["Close"]
  recent = float(close.iloc[-1])
  prior = float(close.iloc[-5])
  if prior <= 0:
    return 0.0
  return (recent - prior) / prior


async def analyze_polymarket(
  session: AsyncSession,
  symbol: str,
  price: float,
  df: pd.DataFrame | None,
  question: str,
) -> PolymarketSignal:
  slug = symbol[3:] if symbol.startswith("PM:") else symbol
  sentiment = await pm_intel_sentiment(session, slug, question)
  momentum = _price_momentum(df)

  score = 0.0
  reasons: list[str] = []
  direction = "hold"

  # Value zone: contrarian Yes entries when price hasn't extreme-settled
  if 0.05 <= price <= 0.55:
    if momentum > 0.008:
      score += 0.35
      reasons.append(f"Yes momentum +{momentum*100:.1f}%")
      direction = "buy"
    elif sentiment > 0.08:
      score += 0.30
      reasons.append(f"Intel bullish ({sentiment:+.2f})")
      direction = "buy"
    elif 0.12 <= price <= 0.38 and sentiment >= -0.05:
      score += 0.20
      reasons.append(f"Value zone Yes @ {price:.2f}")
      direction = "buy"

  if price >= 0.72:
    score -= 0.30
    reasons.append("Yes price overbought (>0.72)")
    direction = "sell"
  elif momentum < -0.04 and df is not None and len(df) >= 15:
    score -= 0.30
    reasons.append(f"Yes momentum {momentum*100:.1f}% (real ticks)")
    direction = "sell"

  if sentiment < -0.20 and direction != "sell":
    score -= 0.25
    reasons.append(f"Intel bearish ({sentiment:+.2f})")
    direction = "sell"

  # Do not flip to sell on value-zone prices when intel is still bullish
  if direction == "sell" and price < 0.55 and sentiment > 0.05:
    direction = "hold"
    reasons.append("Hold: value zone with bullish intel")

  score = max(-1.0, min(1.0, score + sentiment * 0.2 + momentum * 2))
  if direction == "hold" and score >= 0.15:
    direction = "buy"
  elif direction == "hold" and score <= -0.15:
    direction = "sell"

  return PolymarketSignal(
    direction=direction,
    score=abs(score),
    sentiment=sentiment,
    reason="; ".join(reasons) if reasons else f"Yes @ {price:.2f}, sentiment {sentiment:+.2f}",
  )
