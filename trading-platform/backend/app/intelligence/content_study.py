from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.learning_engine import LearningEngine

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
]


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

    result = await self.session.execute(
      select(IntelligenceItem)
      .where(IntelligenceItem.applied.is_(False), IntelligenceItem.relevance_score > 0.5)
      .order_by(IntelligenceItem.fetched_at.desc())
      .limit(20)
    )
    items = list(result.scalars().all())
    applied = 0

    for item in items:
      if abs(item.sentiment) > 0.3 and item.relevance_score > 0.6:
        impact = ""
        if item.sentiment > 0.3:
          impact = f"Bullish sentiment on {item.symbols_mentioned} - favor long entries"
        elif item.sentiment < -0.3:
          impact = f"Bearish sentiment on {item.symbols_mentioned} - tighten stops and reduce long exposure"

        if impact:
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
