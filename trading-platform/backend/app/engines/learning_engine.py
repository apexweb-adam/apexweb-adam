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
    total_loss = sum(t.pnl for t in losing)
    total_profit = sum(t.pnl for t in winning)
    net_pnl = total_profit + total_loss

    patterns: list[str] = []
    if len(losing) > len(winning) and len(day_trades) > 0:
      patterns.append("More losing trades than winning - strategy may need tightening")

    loss_symbols: dict[str, int] = {}
    for t in losing:
      loss_symbols[t.symbol] = loss_symbols.get(t.symbol, 0) + 1
    if loss_symbols:
      worst = max(loss_symbols, key=loss_symbols.get)
      patterns.append(f"Most losses on {worst} ({loss_symbols[worst]} trades)")

    low_signal_losses = [t for t in losing if t.signal_score < 0.5]
    if low_signal_losses:
      patterns.append(f"{len(low_signal_losses)} losses had weak signals (<0.5)")

    conclusions = self._generate_conclusions(day_trades, losing, winning, patterns)
    strategy_changes = await self._generate_strategy_changes(bot_type, patterns, losing)

    review = DailyReview(
      bot_type=bot_type,
      review_date=review_date,
      total_trades=len(day_trades),
      losing_trades=len(losing),
      total_loss=total_loss,
      total_profit=total_profit,
      net_pnl=net_pnl,
      win_rate=len(winning) / len(day_trades) if day_trades else 0,
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

    changed = False
    for adj in adjustments:
      if "min_signal_score" in adj.lower():
        config.min_signal_score = min(0.9, config.min_signal_score + 0.05)
        changed = True
      if "sentiment" in adj.lower() and "positive" in adj.lower():
        config.min_sentiment_score = min(0.5, config.min_sentiment_score + 0.05)
        changed = True
      if "stop-loss" in adj.lower() or "tighten" in adj.lower():
        config.stop_loss_pct = max(0.01, config.stop_loss_pct - 0.002)
        changed = True
      if "position size" in adj.lower() or "smaller positions" in adj.lower():
        config.max_position_pct = max(0.02, config.max_position_pct - 0.005)
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
  ) -> str:
    if not day_trades:
      return "No trades executed today. Bots are scanning for opportunities."

    win_rate = len(winning) / len(day_trades) * 100
    conclusions = [f"Daily win rate: {win_rate:.1f}% ({len(winning)}W / {len(losing)}L)"]

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
    result = await self.session.execute(select(StrategyConfig))
    configs = list(result.scalars().all())

    for config in configs:
      impact_lower = impact.lower()
      if "rsi" in impact_lower and "oversold" in impact_lower:
        config.rsi_oversold = max(25, config.rsi_oversold - 2)
      if "stop" in impact_lower and "tight" in impact_lower:
        config.stop_loss_pct = max(0.01, config.stop_loss_pct - 0.001)
      if "sentiment" in impact_lower:
        config.sentiment_weight = min(0.5, config.sentiment_weight + 0.05)
      config.version += 1
      config.updated_at = datetime.utcnow()
