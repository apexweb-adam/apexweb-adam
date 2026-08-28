from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import DailyReview, IntelligenceItem, LearningInsight, StrategyConfig, Trade, TradeAnalysis


class LearningEngine:
  """Analyzes losing trades, runs daily reviews, and adapts strategy parameters."""

  def __init__(self, session: AsyncSession):
    self.session = session

  async def analyze_losing_trade(self, trade: Trade) -> TradeAnalysis:
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

  async def _get_market_context(self, symbol: str, at_time: datetime) -> str:
    result = await self.session.execute(
      select(IntelligenceItem)
      .where(IntelligenceItem.symbols_mentioned.contains(symbol.replace("USDT", "").replace("=F", "")))
      .order_by(IntelligenceItem.fetched_at.desc())
      .limit(5)
    )
    items = list(result.scalars().all())
    if not items:
      return "No recent intelligence data for this symbol"
    return " | ".join(f"[{i.source}] {i.title}" for i in items)

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

    for config in configs:
      impact_lower = impact.lower()
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
