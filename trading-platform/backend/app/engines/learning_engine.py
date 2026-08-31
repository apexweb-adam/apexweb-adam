from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import DailyReview, IntelligenceItem, LearningInsight, StrategyConfig, Trade, TradeAnalysis

LEARNING_NOISE_DISMISS_MAX_CONFIDENCE = 0.54

_INTEL_LOSS_PATTERN_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
  (("tiktok",), "TikTok/social hype"),
  (("reddit",), "Reddit retail buzz"),
  (("tradingview",), "TradingView webhook"),
  (("youtube",), "YouTube strategy content"),
  (("political", "geopolitical", "tariff"), "Political/macro intel"),
  (("newsapi", "news headline", "breaking news"), "News headline intel"),
  (("fomo",), "fomo copy-trade"),
  (("axiom",), "axiom wallet signal"),
  (("phantom",), "Phantom wallet intel"),
  (("dexscreener",), "DexScreener trending"),
  (("hyperliquid",), "Hyperliquid perp intel"),
  (("wallet_tracker", "whale wallet"), "Whale wallet signal"),
  (("x/twitter", "twitter"), "X/Twitter sentiment"),
  (("polymarket",), "Polymarket account hook"),
]

_INTEL_SOURCE_LABELS: dict[str, str] = {
  "newsapi": "News",
  "wallet_tracker": "Whale",
  "polymarket_account": "Polymarket",
  "tradingview": "TradingView",
  "hyperliquid": "Hyperliquid",
  "dexscreener": "DexScreener",
  "phantom": "Phantom",
  "axiom": "axiom",
  "fomo": "fomo",
  "political": "Political",
  "tiktok": "TikTok",
  "reddit": "Reddit",
  "youtube": "YouTube",
  "x": "X",
}


def intel_source_label(source_type: str) -> str:
  """Human-readable label for intel / content-study source_type values."""
  key = (source_type or "").strip().lower()
  return _INTEL_SOURCE_LABELS.get(key, source_type or "unknown")


def _target_bot_types_from_impact(impact: str) -> set[str] | None:
  """Return bot types mentioned in impact text; None means apply to all configs."""
  text = impact.lower()
  targets: set[str] = set()
  if "target bots:" in text:
    bot_segment = text.split("target bots:", 1)[1].split(";", 1)[0]
    for bot in bot_segment.split(","):
      bot = bot.strip()
      if bot in ("crypto", "stocks_futures", "commodities", "polymarket"):
        targets.add(bot)
    if targets:
      return targets
  if any(
    k in text
    for k in (
      "crypto bot",
      "crypto entries",
      "memecoin",
      "fomo",
      "axiom",
      "phantom",
      "dexscreener",
      "hyperliquid",
      "whale",
      "solana",
      "hl perp",
      "pump.fun",
      "tiktok",
      "reddit retail",
    )
  ):
    targets.add("crypto")
  if any(
    k in text
    for k in ("commodities bot", "gold", "oil", "commodit", "geopolitical")
  ):
    targets.add("commodities")
  if any(
    k in text
    for k in (
      "stocks bot",
      "stocks_futures",
      "stocks_futures bot",
      "futures bot",
      "day-trad",
      "day trad",
      "macd",
      "x/twitter positive",
    )
  ):
    targets.add("stocks_futures")
  if any(k in text for k in ("polymarket", "prediction market", "prediction-market")):
    targets.add("polymarket")
  if "political intel" in text:
    if "commodities" in text:
      targets.add("commodities")
    if "stocks_futures" in text or "stocks bot" in text:
      targets.add("stocks_futures")
    if "crypto" in text:
      targets.add("crypto")
    if "polymarket" in text:
      targets.add("polymarket")
  return targets if targets else None


def collect_intel_pattern_alerts(patterns_found: str | None) -> list[str]:
  """Extract intel-driven loss pattern lines from a daily review patterns string."""
  if not patterns_found:
    return []
  return [
    part.strip()
    for part in patterns_found.split(";")
    if part.strip() and "intel confirmation" in part.lower()
  ]


class LearningEngine:
  """Analyzes losing trades, runs daily reviews, and adapts strategy parameters."""

  def __init__(self, session: AsyncSession):
    self.session = session

  async def analyze_losing_trade(self, trade: Trade) -> TradeAnalysis:
    existing = await self.session.execute(
      select(TradeAnalysis).where(TradeAnalysis.trade_id == trade.id).limit(1)
    )
    prior = existing.scalar_one_or_none()
    if prior:
      return prior

    intel_context = await self._get_market_context(trade.symbol, trade.executed_at)
    sentiment = trade.sentiment_score

    root_causes: list[str] = []
    adjustments: list[str] = []
    lessons: list[str] = []

    if trade.signal_score < 0.5:
      root_causes.append("Weak technical signal at entry")
      adjustments.append("Increase min_signal_score threshold")
      lessons.append("Wait for stronger technical confirmation before entering")

    if sentiment < 0 and trade.side == "long":
      root_causes.append("Entered long position against negative sentiment")
      adjustments.append("Require positive sentiment for long entries")
      lessons.append("Align trade direction with market sentiment")

    if trade.pnl_pct < -3:
      root_causes.append("Loss exceeded normal stop-loss range - possible gap or slippage")
      adjustments.append("Tighten stop-loss or reduce position size in volatile conditions")
      lessons.append("Use smaller positions during high-volatility periods")

    reason_lower = (trade.reason or "").lower()
    fomo_driven = "fomo" in reason_lower or await self._had_source_intel(trade.symbol, trade.executed_at, "fomo")
    axiom_driven = "axiom" in reason_lower or await self._had_source_intel(trade.symbol, trade.executed_at, "axiom")
    phantom_driven = "phantom" in reason_lower or await self._had_source_intel(trade.symbol, trade.executed_at, "phantom")
    if fomo_driven:
      root_causes.append("Entry aligned with fomo.family leaderboard copy-trade signal")
      if trade.signal_score < 0.55:
        root_causes.append("Weak local technical confirmation despite fomo social signal")
        adjustments.append("Require stronger technical score when mirroring fomo leaderboard trades")
        lessons.append("Treat fomo trader buys as intel input — wait for local TA confirmation")
      elif trade.sentiment_score < 0.45:
        root_causes.append("fomo signal present but aggregate sentiment was weak")
        adjustments.append("Require higher sentiment floor for fomo-driven crypto entries")
        lessons.append("Cross-check fomo copy signals with news/social sentiment before entry")

    if axiom_driven:
      root_causes.append("Entry aligned with axiom.trade multi-wallet smart-money signal")
      if trade.signal_score < 0.55:
        adjustments.append("Require stronger technical score when mirroring axiom wallet trades")
        lessons.append("Treat axiom wallet buys as intel — confirm liquidity and volume before entry")
      elif trade.sentiment_score < 0.45:
        adjustments.append("Require higher sentiment floor for axiom-driven memecoin entries")
        lessons.append("Cross-check axiom wallet signals with DexScreener/Hyperliquid before entry")

    if phantom_driven:
      root_causes.append("Entry influenced by Phantom wallet portfolio / watchlist intel")
      adjustments.append("Require TA confirmation when acting on Phantom portfolio moves")
      lessons.append("Phantom wallet changes are sentiment input — not a standalone entry trigger")

    tv_driven = "tradingview" in reason_lower or await self._had_source_intel(
      trade.symbol, trade.executed_at, "tradingview"
    )
    if tv_driven:
      if trade.side == "long" and trade.sentiment_score < 0:
        root_causes.append("Held long against bearish TradingView webhook alert")
        adjustments.append("Honor TradingView sell/bearish alerts for wind-down; do not fight TV exits")
        lessons.append("TradingView alerts are execution signals — exit or reduce when TV flips bearish")
      elif trade.side == "long" and trade.signal_score < 0.5:
        root_causes.append("Entered on TradingView alert without sufficient local composite confirmation")
        adjustments.append("Require composite signal floor when acting on TradingView webhook entries")
        lessons.append("TradingView webhooks augment local TA — wait for aligned signal score before sizing")

    if await self._had_source_intel(trade.symbol, trade.executed_at, "youtube"):
      if trade.signal_score < 0.5:
        root_causes.append("YouTube strategy content influenced entry without local confirmation")
        adjustments.append("Treat YouTube insights as study material — require live signal alignment")
        lessons.append("Apply YouTube playbooks only when composite score and sentiment agree")

    news_driven = (
      "newsapi" in reason_lower
      or "news headline" in reason_lower
      or await self._had_source_intel(trade.symbol, trade.executed_at, "newsapi")
    )
    if news_driven:
      if trade.side == "long" and trade.sentiment_score < 0:
        root_causes.append("Entered long against bearish news headline intel")
        adjustments.append("Honor bearish news sentiment — reduce long exposure when headlines flip negative")
        lessons.append("News headlines move fast — align trade direction with headline sentiment")
      elif trade.signal_score < 0.5:
        root_causes.append("News headline influenced entry without local technical confirmation")
        adjustments.append("Require composite signal floor when acting on news-driven entries")
        lessons.append("Treat news as sentiment input — wait for TA alignment before sizing")

    x_driven = "twitter" in reason_lower or " x " in f" {reason_lower} " or await self._had_source_intel(
      trade.symbol, trade.executed_at, "x"
    )
    if x_driven:
      if trade.side == "long" and trade.sentiment_score < 0:
        root_causes.append("X/Twitter bearish chatter preceded loss on long position")
        adjustments.append("Reduce long exposure when X sentiment flips bearish on the symbol")
        lessons.append("X/Twitter sentiment is fast-moving — honor bearish social intel on open longs")
      elif trade.side == "long" and trade.signal_score < 0.5:
        root_causes.append("X/Twitter sentiment drove entry without technical confirmation")
        adjustments.append("Require composite signal floor when acting on X/Twitter buzz")
        lessons.append("Social buzz on X needs local TA alignment before sizing entries")

    if trade.bot_type == "crypto":
      if await self._had_source_intel(trade.symbol, trade.executed_at, "political"):
        if trade.sentiment_score < 0 and trade.side == "long":
          root_causes.append("Political or crypto-policy intel turned negative during crypto hold")
          adjustments.append("Reduce crypto exposure when policy headlines flip bearish")
          lessons.append("Watch Fed/crypto executive orders and geopolitical risk on BTC/ETH positions")
      if await self._had_source_intel(trade.symbol, trade.executed_at, "tiktok"):
        if trade.side == "long" and (trade.signal_score < 0.5 or trade.sentiment_score < 0.35):
          root_causes.append("TikTok viral sentiment drove entry without sufficient technical confirmation")
          adjustments.append("Require volume + signal floor on TikTok-hype crypto entries")
          lessons.append("Treat TikTok trading trends as sentiment input — confirm with volume before entry")
      if await self._had_source_intel(trade.symbol, trade.executed_at, "reddit"):
        if trade.side == "long" and (trade.signal_score < 0.5 or trade.sentiment_score < 0.35):
          root_causes.append("Reddit retail hype preceded loss without strong local confirmation")
          adjustments.append("Raise min_signal_score when Reddit retail buzz is the primary intel driver")
          lessons.append("WSB/crypto subreddit hype is not a standalone entry — wait for TA alignment")
      if await self._had_source_intel(trade.symbol, trade.executed_at, "dexscreener"):
        if trade.side == "long" and (trade.signal_score < 0.5 or trade.sentiment_score < 0.35):
          root_causes.append("DexScreener trending signal drove entry without volume confirmation")
          adjustments.append("Require volume + liquidity floor on DexScreener hype entries")
          lessons.append("DexScreener boosts are sentiment input — confirm on-chain volume before sizing")
      if await self._had_source_intel(trade.symbol, trade.executed_at, "hyperliquid"):
        if trade.side == "long" and trade.signal_score < 0.5:
          root_causes.append("Hyperliquid perp intel influenced entry without local confirmation")
          adjustments.append("Cross-check HL funding/momentum with local composite before entries")
          lessons.append("Hyperliquid perp signals need TA alignment — watch funding rate flips")
      if await self._had_source_intel(trade.symbol, trade.executed_at, "wallet_tracker"):
        if trade.side == "long" and (trade.signal_score < 0.5 or trade.sentiment_score < 0.35):
          root_causes.append("Whale wallet tracker signal preceded loss without TA confirmation")
          adjustments.append("Require stronger composite score when mirroring whale wallet buys")
          lessons.append("Wallet tracker buys are intel — wait for local signal alignment")

    if trade.bot_type == "stocks_futures":
      if "macd" in reason_lower and "bearish" in reason_lower:
        root_causes.append("Entered against bearish MACD confirmation")
        adjustments.append("Require bullish MACD for stocks_futures entries during gate")
        lessons.append("Wait for MACD bullish crossover before stock entries")
      if any(k in reason_lower for k in ("session close", "wind-down", "afterhours", "outside rth")):
        root_causes.append("Loss during session close or after-hours wind-down")
        adjustments.append("Avoid new entries near session close; tighten wind-down exit rules")
        lessons.append("Respect regular trading hours for stocks day-trading")
      if any(
        k in reason_lower
        for k in ("monday_gate_skip", "session_open_burst", "monday open", "gate-skip")
      ):
        root_causes.append("Loss on Monday session-open or gate-skip auto-entry")
        adjustments.append(
          "Require bullish MACD and volume confirmation on Monday gate-skip entries"
        )
        lessons.append(
          "Gate-skip bypasses chronic blocks at US open — demand stronger technical confirmation"
        )
      if await self._had_source_intel(trade.symbol, trade.executed_at, "political"):
        if trade.sentiment_score < 0 and trade.side == "long":
          root_causes.append("Political intel turned negative during stocks hold")
          adjustments.append("Require positive macro/political sentiment for stocks longs")
          lessons.append("Re-check tariff/Fed/election headlines before holding day-trade positions")
      if await self._had_source_intel(trade.symbol, trade.executed_at, "tiktok"):
        if trade.side == "long" and (trade.signal_score < 0.5 or trade.sentiment_score < 0.35):
          root_causes.append("TikTok viral stock sentiment drove entry without MACD/volume confirmation")
          adjustments.append("Require MACD + volume on TikTok-hype stock entries at session open")
          lessons.append("TikTok stock trends need session-open technical confirmation before day-trade entries")

    if trade.bot_type == "commodities":
      if "weekend" in reason_lower:
        root_causes.append("Commodities position held or exited over weekend session gap")
        adjustments.append("Flat commodities futures before weekend close when possible")
        lessons.append("Weekend gaps on CME metals/energy can gap through stops")
      if any(k in reason_lower for k in ("excess", "cap ", "trim", "close excess")):
        root_causes.append("Forced cap trim — position exceeded gate open-count limit")
        lessons.append("Review position sizing before hitting commodities cap")
      if "macd" in reason_lower and trade.signal_score < 0.5:
        root_causes.append("Weak MACD/technical setup on commodities entry")
        adjustments.append("Raise min_signal_score for commodities during verification")
      if any(
        k in reason_lower
        for k in ("monday_futures_gate_skip", "session_open_burst", "cme reopen", "gate-skip")
      ):
        root_causes.append("Loss on CME reopen or Monday futures gate-skip entry")
        adjustments.append("Raise composite floor for commodities gate-skip entries at session open")
        lessons.append("CME reopen volatility needs extra confirmation before gate-skip entries")
      if await self._had_source_intel(trade.symbol, trade.executed_at, "political"):
        if trade.sentiment_score < 0 and trade.side == "long":
          root_causes.append("Political intel turned negative during commodities hold")
          adjustments.append("Reduce commodities exposure when political headlines flip bearish")
          lessons.append("Weight geopolitical news higher — tighten stops on tariff/geopolitics risk")

    if trade.bot_type == "polymarket":
      if "overbought" in reason_lower:
        root_causes.append("Entered Yes position when share price was overbought (>0.72)")
        adjustments.append("Skip Polymarket entries when Yes price exceeds 0.72 without fresh intel")
        lessons.append("High Yes prices have poor risk/reward — wait for pullback or stronger intel")
      if "momentum" in reason_lower and trade.side == "long" and "bearish" not in reason_lower:
        if "-" in reason_lower or "momentum -" in reason_lower:
          root_causes.append("Yes momentum turned negative after entry")
          adjustments.append("Require stronger Yes momentum confirmation for Polymarket entries")
          lessons.append("Prediction markets can reverse quickly — confirm momentum on real ticks")
      if "intel bearish" in reason_lower and trade.side == "long":
        root_causes.append("Long Yes entry against bearish prediction-market intel")
        adjustments.append("Require positive sentiment for Polymarket Yes entries")
        lessons.append("Align Polymarket direction with macro/political intel sentiment")
      if trade.signal_score < 0.45 and "value zone" not in reason_lower:
        root_causes.append("Weak Polymarket composite signal at entry")
        adjustments.append("Raise min_signal_score for Polymarket during verification")
        lessons.append("Wait for momentum + intel alignment before sizing prediction-market positions")
      if await self._had_source_intel(trade.symbol, trade.executed_at, "political"):
        if trade.sentiment_score < 0 and trade.side == "long":
          root_causes.append("Political intel turned negative after macro Yes entry")
          lessons.append("Re-check political headline risk before holding macro PM positions")
      if await self._had_source_intel(trade.symbol, trade.executed_at, "polymarket_account"):
        if trade.side == "long" and (trade.signal_score < 0.5 or trade.sentiment_score < 0.4):
          root_causes.append("Polymarket account hook signal lacked fresh macro/intel confirmation")
          adjustments.append("Require stronger composite + sentiment when mirroring PM account positions")
          lessons.append("PM account hook is a sync signal — confirm with political/macro intel before Yes entries")

    if not root_causes:
      root_causes.append("Market moved against position - normal variance")
      lessons.append("Review if entry timing could be improved with additional confirmation")

    analysis = TradeAnalysis(
      trade_id=trade.id,
      bot_type=trade.bot_type,
      symbol=trade.symbol,
      loss_amount=abs(trade.pnl),
      root_cause="; ".join(root_causes),
      market_context=intel_context,
      sentiment_at_entry=sentiment,
      technical_signal=trade.reason,
      lessons_learned="; ".join(lessons),
      strategy_adjustment="; ".join(adjustments) if adjustments else "No immediate adjustment needed",
    )
    self.session.add(analysis)
    await self._apply_adjustments(trade.bot_type, adjustments)
    await self.session.commit()
    review_date = (trade.executed_at or datetime.utcnow()).strftime("%Y-%m-%d")
    await self.run_daily_review(trade.bot_type, review_date)
    from app.ws_manager import push_live_update

    await push_live_update()
    return analysis

  async def run_daily_review(self, bot_type: str, review_date: str) -> DailyReview:
    result = await self.session.execute(
      select(Trade).where(
        Trade.bot_type == bot_type,
        Trade.action == "sell",
      )
    )
    all_trades = list(result.scalars().all())
    day_trades = [t for t in all_trades if t.executed_at.strftime("%Y-%m-%d") == review_date]

    losing = [t for t in day_trades if t.is_winner is False]
    winning = [t for t in day_trades if t.is_winner is True]
    breakeven = [t for t in day_trades if t.is_winner is None]
    total_loss = sum(t.pnl for t in losing)
    total_profit = sum(t.pnl for t in winning)
    net_pnl = total_profit + total_loss
    decided = len(winning) + len(losing)
    day_win_rate = len(winning) / decided if decided else 0

    patterns: list[str] = []
    if len(losing) > len(winning) and len(day_trades) > 0:
      patterns.append("More losing trades than winning - strategy may need tightening")

    loss_symbols: dict[str, int] = {}
    for t in losing:
      loss_symbols[t.symbol] = loss_symbols.get(t.symbol, 0) + 1
    if loss_symbols:
      worst = max(loss_symbols, key=loss_symbols.get)
      patterns.append(f"Most losses on {worst} ({loss_symbols[worst]} trades)")
      if loss_symbols[worst] >= 2:
        patterns.append(f"Gate skip recommended for {worst} until win rate recovers")

    low_signal_losses = [t for t in losing if t.signal_score < 0.5]
    if low_signal_losses:
      patterns.append(f"{len(low_signal_losses)} losses had weak signals (<0.5)")

    from app.engines.platform_outage_log import platform_outage_patterns_for_review

    patterns.extend(await platform_outage_patterns_for_review(self.session, review_date))
    patterns.extend(await self._intel_loss_patterns_for_review(losing))

    if bot_type == "polymarket":
      overbought_losses = [
        t for t in losing if "overbought" in (t.reason or "").lower()
      ]
      if overbought_losses:
        patterns.append(
          f"{len(overbought_losses)} Polymarket losses on overbought Yes entries"
        )
      intel_mismatch = [
        t
        for t in losing
        if "intel bearish" in (t.reason or "").lower() or (
          t.sentiment_score < 0 and t.side == "long"
        )
      ]
      if len(intel_mismatch) >= 2:
        patterns.append(
          f"{len(intel_mismatch)} Polymarket losses against bearish intel — tighten sentiment gate"
        )

    conclusions = self._generate_conclusions(day_trades, losing, winning, patterns, breakeven)
    strategy_changes = await self._generate_strategy_changes(bot_type, patterns, losing)

    existing = await self.session.execute(
      select(DailyReview).where(
        DailyReview.bot_type == bot_type,
        DailyReview.review_date == review_date,
      ).limit(1)
    )
    review = existing.scalar_one_or_none()
    if review:
      review.total_trades = len(day_trades)
      review.losing_trades = len(losing)
      review.total_loss = total_loss
      review.total_profit = total_profit
      review.net_pnl = net_pnl
      review.win_rate = day_win_rate
      review.patterns_found = "; ".join(patterns)
      review.conclusions = conclusions
      review.strategy_changes = strategy_changes
      review.created_at = datetime.utcnow()
    else:
      review = DailyReview(
        bot_type=bot_type,
        review_date=review_date,
        total_trades=len(day_trades),
        losing_trades=len(losing),
        total_loss=total_loss,
        total_profit=total_profit,
        net_pnl=net_pnl,
        win_rate=day_win_rate,
        patterns_found="; ".join(patterns),
        conclusions=conclusions,
        strategy_changes=strategy_changes,
      )
      self.session.add(review)
    await self.session.commit()
    return review

  async def apply_external_insight(
    self,
    source_type: str,
    title: str,
    url: str,
    takeaways: str,
    impact: str,
    confidence: float,
  ) -> LearningInsight:
    existing = await self.session.execute(
      select(LearningInsight).where(
        LearningInsight.source_url == url,
        LearningInsight.source_title == title,
      ).limit(1)
    )
    prior = existing.scalars().first()
    if prior:
      return prior

    insight = LearningInsight(
      source_type=source_type,
      source_title=title,
      source_url=url,
      key_takeaways=takeaways,
      strategy_impact=impact,
      confidence=confidence,
    )
    self.session.add(insight)

    if confidence >= 0.6 and impact:
      await self._apply_insight_to_strategies(impact)

    insight.applied = confidence >= 0.6
    await self.session.commit()
    return insight

  async def apply_pending_insights(self, min_confidence: float = 0.55) -> int:
    """Apply stored insights that were not yet applied to strategy configs."""
    result = await self.session.execute(
      select(LearningInsight).where(
        LearningInsight.applied.is_(False),
        LearningInsight.confidence >= min_confidence,
      )
    )
    applied = 0
    for insight in result.scalars().all():
      if insight.strategy_impact:
        await self._apply_insight_to_strategies(insight.strategy_impact)
      insight.applied = True
      applied += 1
    if applied:
      await self.session.commit()
    return applied

  async def dismiss_noise_insights(self, max_confidence: float = 0.5) -> int:
    """Mark low-confidence intel-derived insights as applied without strategy changes."""
    result = await self.session.execute(
      select(LearningInsight).where(
        LearningInsight.applied.is_(False),
        LearningInsight.confidence < max_confidence,
      )
    )
    dismissed = 0
    for insight in result.scalars().all():
      insight.applied = True
      dismissed += 1
    if dismissed:
      await self.session.commit()
    return dismissed

  async def _intel_loss_patterns_for_review(self, losing: list) -> list[str]:
    """Surface recurring intel-driven loss themes in daily post-mortems."""
    if len(losing) < 2:
      return []
    trade_ids = [
      t.id for t in losing if isinstance(getattr(t, "id", None), int)
    ]
    analyses_by_trade: dict[int, str] = {}
    if trade_ids:
      result = await self.session.execute(
        select(TradeAnalysis).where(TradeAnalysis.trade_id.in_(trade_ids))
      )
      for analysis in result.scalars().all():
        analyses_by_trade[analysis.trade_id] = (
          f"{analysis.root_cause} {analysis.lessons_learned}".lower()
        )

    counts: dict[str, int] = {}
    for trade in losing:
      blob = f"{trade.reason or ''} {analyses_by_trade.get(trade.id, '')}".lower()
      for keywords, label in _INTEL_LOSS_PATTERN_KEYWORDS:
        if any(keyword in blob for keyword in keywords):
          counts[label] = counts.get(label, 0) + 1

    patterns: list[str] = []
    for label, count in counts.items():
      if count >= 2:
        patterns.append(f"{count} losses tied to {label} — tighten intel confirmation gates")
    return patterns

  async def _had_source_intel(self, symbol: str, at_time: datetime | None, source: str) -> bool:
    """True when recent intel from a source mentioned this symbol near trade time."""
    from datetime import timedelta

    base = at_time or datetime.utcnow()
    cutoff = base - timedelta(hours=6)
    needle = symbol.replace("USDT", "").replace("=F", "").upper()
    result = await self.session.execute(
      select(IntelligenceItem)
      .where(
        IntelligenceItem.source == source,
        IntelligenceItem.fetched_at >= cutoff,
      )
      .order_by(IntelligenceItem.fetched_at.desc())
      .limit(20)
    )
    for item in result.scalars().all():
      mentioned = (item.symbols_mentioned or "").upper()
      if needle in mentioned or symbol.upper() in mentioned:
        return True
    return False

  async def _had_fomo_intel(self, symbol: str, at_time: datetime | None) -> bool:
    return await self._had_source_intel(symbol, at_time, "fomo")

  async def _get_market_context(self, symbol: str, at_time: datetime) -> str:
    needle = symbol.replace("USDT", "").replace("=F", "").upper()
    result = await self.session.execute(
      select(IntelligenceItem)
      .where(IntelligenceItem.symbols_mentioned.contains(needle))
      .order_by(IntelligenceItem.fetched_at.desc())
      .limit(8)
    )
    items = list(result.scalars().all())
    if not items:
      return "No recent intelligence data for this symbol"
    priority_sources = {"fomo", "axiom", "phantom"}
    ordered = sorted(
      items,
      key=lambda i: (0 if i.source in priority_sources else 1, -i.fetched_at.timestamp()),
    )
    parts: list[str] = []
    for item in ordered[:5]:
      tag = item.source
      if item.source in priority_sources and item.title:
        tag = f"{item.source}:{item.title[:48]}"
      parts.append(f"[{tag}] {item.title}")
    return " | ".join(parts)

  async def _apply_adjustments(self, bot_type: str, adjustments: list[str]) -> None:
    if not adjustments:
      return

    result = await self.session.execute(
      select(StrategyConfig).where(StrategyConfig.bot_type == bot_type)
    )
    config = result.scalar_one_or_none()
    if not config:
      return

    from app.config import settings
    from app.engines.strategy_migration import cap_verification_signal_score

    pm_cap = settings.polymarket_max_position_pct
    changed = False
    for adj in adjustments:
      if "min_signal_score" in adj.lower():
        config.min_signal_score = cap_verification_signal_score(
          bot_type, min(0.9, config.min_signal_score + 0.05)
        )
        changed = True
      if "sentiment" in adj.lower() and "positive" in adj.lower():
        config.min_sentiment_score = min(0.5, config.min_sentiment_score + 0.05)
        changed = True
      if "stop-loss" in adj.lower() or "tighten" in adj.lower():
        floor = settings.polymarket_stop_loss_pct if bot_type == "polymarket" else 0.01
        config.stop_loss_pct = max(floor, config.stop_loss_pct - 0.002)
        changed = True
      if "position size" in adj.lower() or "smaller positions" in adj.lower():
        floor = pm_cap if bot_type == "polymarket" else 0.02
        config.max_position_pct = max(floor, config.max_position_pct - 0.005)
        if bot_type == "polymarket":
          config.max_position_pct = min(config.max_position_pct, pm_cap)
        changed = True

    if bot_type == "polymarket":
      if config.max_position_pct > pm_cap:
        config.max_position_pct = pm_cap
        changed = True

    if changed:
      config.version += 1
      config.updated_at = datetime.utcnow()

  def _generate_conclusions(
    self,
    day_trades: list,
    losing: list,
    winning: list,
    patterns: list[str],
    breakeven: list | None = None,
  ) -> str:
    if not day_trades:
      return "No trades executed today. Bots are scanning for opportunities."

    breakeven = breakeven or []
    decided = len(winning) + len(losing)
    win_rate = (len(winning) / decided * 100) if decided else 0
    record = f"{len(winning)}W / {len(losing)}L"
    if breakeven:
      record += f" / {len(breakeven)}BE"
    conclusions = [f"Daily win rate: {win_rate:.1f}% ({record})"]

    if win_rate < 50:
      conclusions.append("Below target win rate - strategy parameters will be tightened")
    elif win_rate >= 60:
      conclusions.append("Strong performance - maintaining current strategy with minor optimizations")

    if patterns:
      conclusions.append(f"Key patterns: {'; '.join(patterns)}")

    return " | ".join(conclusions)

  async def _generate_strategy_changes(
    self,
    bot_type: str,
    patterns: list[str],
    losing: list,
  ) -> str:
    changes: list[str] = []

    if any("weak signals" in p for p in patterns):
      changes.append("Raised minimum signal score threshold by 0.05")
      await self._apply_adjustments(bot_type, ["Increase min_signal_score threshold"])

    if any("intel confirmation" in p for p in patterns):
      changes.append("Tightened intel confirmation gates after recurring social/macro-driven losses")
      await self._apply_adjustments(
        bot_type,
        [
          "Require positive sentiment for long entries",
          "Increase min_signal_score threshold",
        ],
      )

    if len(losing) > 3:
      changes.append("Reduced max position size due to elevated daily losses")
      await self._apply_adjustments(bot_type, ["Use smaller positions during high-volatility periods"])

    if not changes:
      changes.append("No strategy changes needed - performance within acceptable range")

    return "; ".join(changes)

  async def _apply_insight_to_strategies(self, impact: str) -> None:
    from app.config import settings

    result = await self.session.execute(select(StrategyConfig))
    configs = list(result.scalars().all())
    targets = _target_bot_types_from_impact(impact)
    impact_lower = impact.lower()

    for config in configs:
      if targets is not None and config.bot_type not in targets:
        continue
      changed = False
      if "rsi" in impact_lower and "oversold" in impact_lower:
        config.rsi_oversold = max(25, config.rsi_oversold - 2)
        changed = True
      if "stop" in impact_lower and "tight" in impact_lower:
        floor = (
          settings.polymarket_stop_loss_pct
          if config.bot_type == "polymarket"
          else 0.01
        )
        config.stop_loss_pct = max(floor, config.stop_loss_pct - 0.001)
        changed = True
      if "sentiment" in impact_lower:
        config.sentiment_weight = min(0.5, config.sentiment_weight + 0.05)
        changed = True
      if "technical_weight" in impact_lower or "tradingview" in impact_lower:
        config.technical_weight = min(0.6, config.technical_weight + 0.05)
        changed = True
      # Never raise Polymarket position size from external content (0–1 share math)
      if "position" in impact_lower and config.bot_type != "polymarket":
        if "reduce" in impact_lower or "smaller" in impact_lower or "2%" in impact_lower:
          config.max_position_pct = max(0.03, config.max_position_pct - 0.005)
          changed = True
      if config.bot_type == "polymarket":
        capped = min(config.max_position_pct, settings.polymarket_max_position_pct)
        if capped != config.max_position_pct:
          config.max_position_pct = capped
          changed = True
      if changed:
        config.version += 1
        config.updated_at = datetime.utcnow()


async def build_crm_learning_highlights(session: AsyncSession) -> dict[str, Any]:
  """Summarize today's learning loop for the /crm landing page."""
  today = datetime.utcnow().strftime("%Y-%m-%d")
  reviews_result = await session.execute(
    select(DailyReview)
    .where(DailyReview.review_date == today)
    .order_by(DailyReview.bot_type)
  )
  reviews = list(reviews_result.scalars().all())
  analysis_count = int(
    await session.scalar(select(func.count(TradeAnalysis.id))) or 0
  )
  pending_insights = int(
    await session.scalar(
      select(func.count(LearningInsight.id)).where(LearningInsight.applied.is_(False))
    )
    or 0
  )

  active_reviews: list[dict[str, Any]] = []
  intel_pattern_alerts: list[str] = []
  for review in reviews:
    if review.total_trades <= 0 and not (review.patterns_found or "").strip():
      continue
    for alert in collect_intel_pattern_alerts(review.patterns_found):
      intel_pattern_alerts.append(f"{review.bot_type}: {alert}")
    active_reviews.append(
      {
        "bot_type": review.bot_type,
        "total_trades": review.total_trades,
        "losing_trades": review.losing_trades,
        "win_rate": review.win_rate,
        "net_pnl": review.net_pnl,
        "patterns_found": review.patterns_found or "",
        "strategy_changes": review.strategy_changes or "",
        "conclusions": review.conclusions or "",
      }
    )

  return {
    "review_date": today,
    "trade_analyses": analysis_count,
    "pending_insights": pending_insights,
    "intel_pattern_alerts": intel_pattern_alerts,
    "reviews": active_reviews,
  }


async def build_crm_content_study_highlights(
  session: AsyncSession,
  *,
  limit: int = 5,
) -> dict[str, Any]:
  """Summarize recent external content-study insights for the /crm landing page."""
  result = await session.execute(
    select(LearningInsight)
    .order_by(desc(LearningInsight.created_at))
    .limit(limit)
  )
  insights = list(result.scalars().all())
  applied_total = int(
    await session.scalar(
      select(func.count(LearningInsight.id)).where(LearningInsight.applied.is_(True))
    )
    or 0
  )

  recent: list[dict[str, Any]] = []
  for insight in insights:
    title = insight.source_title or "Untitled"
    if len(title) > 72:
      title = f"{title[:69]}…"
    impact = insight.strategy_impact or ""
    if len(impact) > 120:
      impact = f"{impact[:117]}…"
    recent.append(
      {
        "source_type": insight.source_type,
        "title": title,
        "impact": impact,
        "confidence": insight.confidence,
        "applied": bool(insight.applied),
      }
    )

  return {
    "insights_applied": applied_total,
    "recent": recent,
  }


async def analyze_losing_trade_for_symbol(
  session: AsyncSession,
  bot_type: str,
  symbol: str,
) -> TradeAnalysis | None:
  """Run post-mortem on the most recent losing sell for a symbol (migration/trim paths)."""
  result = await session.execute(
    select(Trade)
    .where(
      Trade.bot_type == bot_type,
      Trade.symbol == symbol,
      Trade.action == "sell",
    )
    .order_by(Trade.executed_at.desc())
    .limit(1)
  )
  trade = result.scalar_one_or_none()
  if trade and trade.is_winner is False:
    return await LearningEngine(session).analyze_losing_trade(trade)
  return None
