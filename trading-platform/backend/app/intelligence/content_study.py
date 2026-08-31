from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.learning_engine import LearningEngine

# Keyword patterns extracted from YouTube/podcast titles → structured strategy impacts.
YOUTUBE_IMPACT_PATTERNS: list[tuple[tuple[str, ...], str, float]] = [
  (("rsi", "divergence"), "Lower RSI oversold threshold for divergence entries; require volume confirmation", 0.78),
  (("support", "resistance"), "Favor entries near support levels; add S/R confirmation to signal engine", 0.8),
  (("risk management", "position size"), "Tighten stop-loss to 1.5-2% max; reduce max position size", 0.88),
  (("stop loss", "stop-loss"), "Tighten stop-loss; cut losses quickly on failed setups", 0.85),
  (("trend following", "momentum"), "Increase momentum weight; let winners run with wider take-profit", 0.82),
  (("sentiment", "social"), "Increase sentiment weight for crypto; monitor X/TikTok/Reddit feeds", 0.75),
  (("gold", "commodit"), "Weight geopolitical news higher for commodities bot", 0.72),
  (("crypto", "bitcoin", "ethereum"), "Increase sentiment weight for crypto bot on social signals", 0.74),
  (("volume", "breakout"), "Require volume confirmation on breakout entries", 0.8),
  (("revenge", "psychology", "discipline"), "After loss streaks raise signal threshold and halve position size", 0.85),
  (("polymarket", "prediction market"), "Weight Polymarket intel for event-driven setups", 0.7),
  (("memecoin", "pump"), "Tighten memecoin entries: require volume + social confirmation; cut fast on -3%", 0.88),
  (("solana", "meme"), "Boost sentiment weight for SOL memecoins; track DexScreener + whale wallets", 0.86),
  (("hyperliquid", "perp"), "Use HL funding rate as contrarian signal; favor momentum on kPEPE/WIF/BONK", 0.84),
  (("pump.fun", "degen"), "Never chase illiquid launches; min liquidity gate before entry", 0.9),
  (("day trad", "scalp"), "Focus on higher signal scores during day-trading sessions", 0.72),
]


def _extract_youtube_impact(title: str, content: str) -> tuple[str, float] | None:
  text = f"{title} {content}".lower()
  for keywords, impact, confidence in YOUTUBE_IMPACT_PATTERNS:
    if all(kw in text for kw in keywords):
      return impact, confidence
  return None


TRADING_KNOWLEDGE_BASE = [
  {
    "source_type": "youtube",
    "title": "RSI Divergence Trading Strategy",
    "url": "https://www.youtube.com/results?search_query=rsi+divergence+trading",
    "takeaways": "RSI divergence between price and indicator signals potential reversals. Use with volume confirmation.",
    "impact": "Lower RSI oversold threshold to catch earlier entries on divergence setups. Require volume confirmation.",
    "confidence": 0.75,
  },
  {
    "source_type": "youtube",
    "title": "Risk Management - Never Risk More Than 2%",
    "url": "https://www.youtube.com/results?search_query=trading+risk+management+2+percent",
    "takeaways": "Professional traders never risk more than 1-2% per trade. Position sizing is more important than entry timing.",
    "impact": "Tighten stop-loss to 1.5-2% max. Reduce max position size to 3-5% of portfolio.",
    "confidence": 0.9,
  },
  {
    "source_type": "podcast",
    "title": "Market Wizards - Trend Following",
    "url": "https://www.youtube.com/results?search_query=market+wizards+trend+following",
    "takeaways": "Cut losses quickly, let winners run. Trend following works best with momentum confirmation.",
    "impact": "Increase take-profit ratio to 2:1 or 3:1. Add momentum weight to composite signal.",
    "confidence": 0.85,
  },
  {
    "source_type": "youtube",
    "title": "Crypto Trading - Sentiment Analysis",
    "url": "https://www.youtube.com/results?search_query=crypto+sentiment+analysis+trading",
    "takeaways": "Social sentiment leads price in crypto markets. Reddit and Twitter sentiment are leading indicators.",
    "impact": "Increase sentiment weight for crypto bot. Monitor social feeds more frequently.",
    "confidence": 0.7,
  },
  {
    "source_type": "youtube",
    "title": "Support and Resistance Trading",
    "url": "https://www.youtube.com/results?search_query=support+resistance+day+trading",
    "takeaways": "Trade bounces off key support/resistance levels. Combine with RSI for higher probability entries.",
    "impact": "Add support/resistance detection to signal engine. Enter only near key levels.",
    "confidence": 0.8,
  },
  {
    "source_type": "podcast",
    "title": "Trading Psychology - Avoiding Revenge Trading",
    "url": "https://www.youtube.com/results?search_query=trading+psychology+revenge+trading",
    "takeaways": "After a losing streak, reduce position size and wait for A+ setups. Never chase losses.",
    "impact": "After 3 consecutive losses, halve position size and raise signal threshold.",
    "confidence": 0.85,
  },
  {
    "source_type": "youtube",
    "title": "Gold Trading Strategies",
    "url": "https://www.youtube.com/results?search_query=gold+trading+strategy+2024",
    "takeaways": "Gold correlates with USD strength and geopolitical events. Trade during London/NY overlap.",
    "impact": "Weight geopolitical news higher for commodities bot. Focus trading during peak hours.",
    "confidence": 0.7,
  },
  {
    "source_type": "reddit",
    "title": "r/Daytrading Wiki - Core Principles",
    "url": "https://www.reddit.com/r/Daytrading/wiki/index",
    "takeaways": "Volume confirms price action. Low volume breakouts are unreliable. Always check volume.",
    "impact": "Add volume confirmation requirement to entry signals.",
    "confidence": 0.8,
  },
  {
    "source_type": "youtube",
    "title": "Solana Memecoin Trading - Pump.fun & DexScreener",
    "url": "https://www.youtube.com/results?search_query=solana+memecoin+trading+pump.fun",
    "takeaways": "Track whale wallets and DexScreener boosts. Cut losers fast; memecoins move in minutes not hours.",
    "impact": "Increase sentiment weight for crypto on social/whale signals. Tighten stop-loss on memecoin pairs.",
    "confidence": 0.82,
  },
  {
    "source_type": "youtube",
    "title": "Hyperliquid Perps Trading Guide",
    "url": "https://www.youtube.com/results?search_query=hyperliquid+perpetual+trading",
    "takeaways": "HL perps offer leverage on memecoins. Watch funding rates and 24h momentum before entries.",
    "impact": "Weight Hyperliquid intel for crypto entries on WIF/PEPE/BONK. Use funding as contrarian filter.",
    "confidence": 0.8,
  },
]


def _is_trading_relevant_intel(title: str, content: str, source: str) -> bool:
  """Skip sports betting and irrelevant prediction-market noise for learning insights."""
  text = f"{title} {content}".lower()
  noise_markers = (
    "spread:", "o/u ", "over/under", "bo3)", "bo5)",
    "counter-strike", " vs. ", " vs ", "mlb-", "nfl-", "nba-",
    "will win the 2026", "will win the 2027", "will win the 2028",
    "presidential nomination", "republican nomination", "democratic nomination",
    "uefa champions",
    "counter-strike:", "dota", "valorant",
  )
  if any(marker in text for marker in noise_markers):
    return False
  if source in ("polymarket", "polymarket_account") and not any(
    kw in text for kw in ("crypto", "bitcoin", "ethereum", "fed", "rate", "election", "trump", "tariff", "oil", "gold")
  ):
    return False
  return True


LIVE_INTEL_SOURCES = (
  "fomo",
  "axiom",
  "phantom",
  "dexscreener",
  "hyperliquid",
  "wallet_tracker",
  "x",
  "tiktok",
  "reddit",
  "tradingview",
  "political",
)


def _extract_political_impact(
  title: str,
  content: str,
  symbols: str,
  sentiment: float,
  relevance: float,
) -> tuple[str, float] | None:
  """Map political headlines into bot-targeted strategy impacts."""
  from app.intelligence.political_signals import classify_political_event

  text = f"{title} {content}"
  event_type, event_symbols, target_bots = classify_political_event(text)
  if abs(sentiment) < 0.1 and event_type == "general":
    return None
  sym = symbols or ",".join(event_symbols[:3])
  bots = ", ".join(target_bots)
  if sentiment > 0.1:
    direction = "long"
  elif sentiment < -0.1:
    direction = "cautious"
  else:
    direction = "defensive"
  impact = (
    f"Political intel ({event_type}): favor {direction} bias on {sym} — "
    f"target bots: {bots}; weight geopolitical news when price action aligns"
  )
  confidence = min(0.82, relevance * 0.85 + abs(sentiment) * 0.15)
  if confidence < 0.55:
    return None
  return impact, confidence


def _extract_live_intel_impact(source: str, title: str, content: str, symbols: str, sentiment: float, relevance: float) -> tuple[str, float] | None:
  """Map live scanner intel into bot-targeted strategy impacts."""
  text = f"{title} {content}".lower()
  sym = symbols or "markets"

  if source == "fomo":
    if sentiment > 0.15:
      return (
        f"fomo.family leaderboard buy on {sym} — crypto bot: require local TA confirmation before mirroring copy trades; increase sentiment weight",
        min(0.85, relevance * 0.85 + abs(sentiment) * 0.25),
      )
    if sentiment < -0.15:
      return (
        f"fomo.family sell signal on {sym} — crypto bot: tighten stop-loss and avoid chasing leaderboard exits",
        min(0.8, relevance * 0.8 + abs(sentiment) * 0.2),
      )
    return None

  if source == "axiom":
    if sentiment > 0.15:
      return (
        f"axiom.trade multi-wallet buy on {sym} — crypto bot: require liquidity + volume before mirroring smart-money entries",
        min(0.87, relevance * 0.88 + abs(sentiment) * 0.2),
      )
    if sentiment < -0.15:
      return (
        f"axiom.trade wallet distribution on {sym} — crypto bot: tighten stop-loss; avoid chasing wallet exits",
        min(0.82, relevance * 0.85),
      )
    return None

  if source == "phantom":
    if sentiment > 0.1 or "accumul" in text or "buy" in text:
      return (
        f"Phantom wallet accumulation on {sym} — crypto bot: treat portfolio moves as sentiment input with TA confirmation",
        min(0.8, relevance * 0.86),
      )
    if sentiment < -0.1 or "sell" in text or "dump" in text:
      return (
        f"Phantom wallet distribution on {sym} — crypto bot: reduce size on wallet-led exits",
        min(0.78, relevance * 0.82),
      )
    return None

  if source == "dexscreener":
    if "boost" in text or sentiment > 0.2:
      return (
        f"DexScreener trending {sym} — crypto bot: require volume + liquidity confirmation; tighten stop-loss on memecoin entries",
        min(0.84, relevance * 0.9),
      )
    if sentiment < -0.2:
      return (
        f"DexScreener weakness on {sym} — crypto bot: reduce long exposure and tighten stops",
        min(0.78, relevance * 0.85),
      )
    return None

  if source == "hyperliquid":
    if "funding" in text and sentiment < 0:
      return (
        f"Hyperliquid negative funding on {sym} — crypto bot: use funding as contrarian long filter; favor momentum on HL perps",
        min(0.82, relevance * 0.88),
      )
    if sentiment > 0.15:
      return (
        f"Hyperliquid perp momentum on {sym} — crypto bot: weight HL intel for entries; let winners run with wider take-profit",
        min(0.8, relevance * 0.85 + abs(sentiment) * 0.15),
      )
    return None

  if source == "wallet_tracker":
    if sentiment > 0.2 or "buy" in text or "accumul" in text:
      return (
        f"Whale wallet accumulation on {sym} — crypto bot: follow wallet intel with volume confirmation; increase sentiment weight",
        min(0.83, relevance * 0.9 + abs(sentiment) * 0.1),
      )
    if sentiment < -0.2 or "sell" in text or "dump" in text:
      return (
        f"Whale wallet distribution on {sym} — crypto bot: tighten stops and reduce position size on whale exits",
        min(0.8, relevance * 0.85),
      )
    return None

  if source == "x":
    if sentiment > 0.25:
      if any(k in text for k in ("crypto", "bitcoin", "btc", "meme", "solana")):
        return (
          f"X/Twitter bullish buzz on {sym} — crypto bot: increase sentiment weight when social aligns with TA",
          min(0.78, relevance * 0.85 + abs(sentiment) * 0.15),
        )
      return (
        f"X/Twitter positive sentiment on {sym} — stocks_futures bot: favor long bias when sentiment confirms",
        min(0.72, relevance * 0.8 + abs(sentiment) * 0.1),
      )
    if sentiment < -0.25:
      return (
        f"X/Twitter bearish chatter on {sym} — tighten stop-loss and reduce long exposure",
        min(0.75, relevance * 0.82),
      )
    return None

  if source == "tiktok":
    if relevance > 0.45 and any(k in text for k in ("meme", "crypto", "bitcoin", "solana", "pump")):
      return (
        f"TikTok viral trading sentiment on {sym} — crypto bot: require volume confirmation on social-driven entries",
        min(0.76, relevance * 0.88),
      )
    if relevance > 0.45 and any(
      k in text for k in ("stock", "aapl", "nvda", "tsla", "spy", "qqq", "day trad", "earnings", "options")
    ):
      return (
        f"TikTok viral stock sentiment on {sym} — stocks_futures bot: require MACD + volume at session open",
        min(0.74, relevance * 0.85),
      )
    return None

  if source == "reddit":
    if sentiment > 0.2:
      if any(k in text for k in ("wsb", "wallstreetbets", "yolo", "meme", "cryptocurrency")):
        return (
          f"Reddit retail buzz on {sym} — crypto bot: treat social hype as sentiment input, not sole entry signal",
          min(0.74, relevance * 0.85 + abs(sentiment) * 0.1),
        )
      return (
        f"Reddit bullish discussion on {sym} — increase sentiment weight when aligned with technical signals",
        min(0.7, relevance * 0.8),
      )
    if sentiment < -0.2:
      return (
        f"Reddit bearish thread on {sym} — avoid counter-trend longs; tighten stops on open positions",
        min(0.72, relevance * 0.8),
      )
    return None

  if source == "tradingview":
    if sentiment > 0 or any(k in text for k in ("buy", "long", "bullish")):
      return (
        f"TradingView alert on {sym} — require webhook signal alignment before entry; increase technical_weight",
        min(0.8, relevance * 0.9),
      )
    if sentiment < 0 or any(k in text for k in ("sell", "short", "bearish")):
      return (
        f"TradingView exit signal on {sym} — honor TV alerts for wind-down; avoid fighting the alert",
        min(0.78, relevance * 0.85),
      )
    return None

  if source == "political":
    return _extract_political_impact(title, content, symbols, sentiment, relevance)

  return None


class ContentStudyEngine:
  """Studies trading content from YouTube, podcasts, Reddit, and applies insights to strategy."""

  def __init__(self, session: AsyncSession):
    self.session = session
    self.learner = LearningEngine(session)

  async def study_and_apply(self) -> int:
    applied = 0
    for item in TRADING_KNOWLEDGE_BASE:
      insight = await self.learner.apply_external_insight(
        source_type=item["source_type"],
        title=item["title"],
        url=item["url"],
        takeaways=item["takeaways"],
        impact=item["impact"],
        confidence=item["confidence"],
      )
      if insight.applied:
        applied += 1
    return applied

  async def study_from_intelligence(self) -> int:
    """Extract trading insights from collected intelligence items."""
    from sqlalchemy import select

    from app.models.entities import IntelligenceItem

    applied = 0
    applied += await self._study_live_intel_sources()

    youtube_result = await self.session.execute(
      select(IntelligenceItem)
      .where(
        IntelligenceItem.applied.is_(False),
        IntelligenceItem.source == "youtube",
        IntelligenceItem.relevance_score > 0.4,
      )
      .order_by(IntelligenceItem.fetched_at.desc())
      .limit(10)
    )
    for item in youtube_result.scalars().all():
      extracted = _extract_youtube_impact(item.title, item.content or "")
      if extracted:
        impact, confidence = extracted
      else:
        impact = (
          f"YouTube intel on {item.symbols_mentioned or 'markets'}: "
          f"favor {'long' if item.sentiment > 0 else 'cautious'} setups when sentiment aligns"
        )
        confidence = min(0.85, item.relevance_score)
      insight = await self.learner.apply_external_insight(
        source_type="youtube",
        title=item.title,
        url=item.url,
        takeaways=item.content[:500],
        impact=impact,
        confidence=confidence,
      )
      if insight.applied:
        item.applied = True
        applied += 1

    event_result = await self.session.execute(
      select(IntelligenceItem)
      .where(
        IntelligenceItem.applied.is_(False),
        IntelligenceItem.source.in_(("political", "polymarket", "polymarket_account")),
        IntelligenceItem.relevance_score > 0.3,
      )
      .order_by(IntelligenceItem.fetched_at.desc())
      .limit(15)
    )
    for item in event_result.scalars().all():
      if abs(item.sentiment) < 0.1:
        item.applied = True
        continue
      if not _is_trading_relevant_intel(item.title, item.content or "", item.source):
        item.applied = True
        continue
      if item.source == "political":
        extracted = _extract_political_impact(
          item.title,
          item.content or "",
          item.symbols_mentioned or "",
          float(item.sentiment or 0),
          float(item.relevance_score or 0),
        )
        if extracted:
          impact, confidence = extracted
          insight = await self.learner.apply_external_insight(
            source_type=item.source,
            title=item.title,
            url=item.url or "",
            takeaways=item.content[:500],
            impact=impact,
            confidence=confidence,
          )
          if insight.applied:
            item.applied = True
            applied += 1
          continue
      direction = "long" if item.sentiment > 0 else "cautious"
      symbols = item.symbols_mentioned or "macro markets"
      impact = (
        f"Event intel ({item.source}): favor {direction} bias on {symbols} "
        f"when prediction-market and price action align"
      )
      insight = await self.learner.apply_external_insight(
        source_type=item.source,
        title=item.title,
        url=item.url or "",
        takeaways=item.content[:500],
        impact=impact,
        confidence=min(0.75, item.relevance_score * (0.5 + abs(item.sentiment))),
      )
      if insight.applied:
        item.applied = True
        applied += 1

    result = await self.session.execute(
      select(IntelligenceItem)
      .where(IntelligenceItem.applied.is_(False), IntelligenceItem.relevance_score > 0.5)
      .order_by(IntelligenceItem.fetched_at.desc())
      .limit(20)
    )
    items = list(result.scalars().all())

    for item in items:
      if not _is_trading_relevant_intel(item.title, item.content or "", item.source):
        item.applied = True
        continue
      if abs(item.sentiment) > 0.3 and item.relevance_score > 0.6:
        impact = ""
        if item.sentiment > 0.3:
          impact = f"Bullish sentiment on {item.symbols_mentioned} - favor long entries"
        elif item.sentiment < -0.3:
          impact = f"Bearish sentiment on {item.symbols_mentioned} - tighten stops and reduce long exposure"

        if impact:
          confidence = item.relevance_score * abs(item.sentiment)
          if confidence < 0.5:
            item.applied = True
            continue
          await self.learner.apply_external_insight(
            source_type=item.source,
            title=item.title,
            url=item.url,
            takeaways=item.content[:500],
            impact=impact,
            confidence=item.relevance_score * abs(item.sentiment),
          )
          item.applied = True
          applied += 1

    await self.session.commit()
    return applied

  async def _study_live_intel_sources(self) -> int:
    """Turn fomo/dexscreener/hyperliquid/wallet intel into crypto-targeted insights."""
    from sqlalchemy import select

    from app.models.entities import IntelligenceItem

    applied = 0
    result = await self.session.execute(
      select(IntelligenceItem)
      .where(
        IntelligenceItem.applied.is_(False),
        IntelligenceItem.source.in_(LIVE_INTEL_SOURCES),
        IntelligenceItem.relevance_score > 0.45,
      )
      .order_by(IntelligenceItem.fetched_at.desc())
      .limit(25)
    )
    for item in result.scalars().all():
      if not _is_trading_relevant_intel(item.title, item.content or "", item.source):
        item.applied = True
        continue
      extracted = _extract_live_intel_impact(
        item.source,
        item.title,
        item.content or "",
        item.symbols_mentioned or "",
        float(item.sentiment or 0),
        float(item.relevance_score or 0),
      )
      if not extracted:
        item.applied = True
        continue
      impact, confidence = extracted
      if confidence < 0.55:
        item.applied = True
        continue
      insight = await self.learner.apply_external_insight(
        source_type=item.source,
        title=item.title,
        url=item.url or f"{item.source}:{item.id}",
        takeaways=(item.content or "")[:500],
        impact=impact,
        confidence=confidence,
      )
      item.applied = True
      if insight.applied:
        applied += 1
    await self.session.commit()
    return applied
