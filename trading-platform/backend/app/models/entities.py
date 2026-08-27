from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_type: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    balance: Mapped[float] = mapped_column(Float, default=100_000.0)
    equity: Mapped[float] = mapped_column(Float, default=100_000.0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_type: Mapped[str] = mapped_column(String(50), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    side: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_type: Mapped[str] = mapped_column(String(50), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    side: Mapped[str] = mapped_column(String(10))
    action: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    is_winner: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    strategy: Mapped[str] = mapped_column(String(100), default="default")
    signal_score: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TradeAnalysis(Base):
    __tablename__ = "trade_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_id: Mapped[int] = mapped_column(Integer, index=True)
    bot_type: Mapped[str] = mapped_column(String(50))
    symbol: Mapped[str] = mapped_column(String(30))
    loss_amount: Mapped[float] = mapped_column(Float)
    root_cause: Mapped[str] = mapped_column(Text)
    market_context: Mapped[str] = mapped_column(Text)
    sentiment_at_entry: Mapped[float] = mapped_column(Float, default=0.0)
    technical_signal: Mapped[str] = mapped_column(Text, default="")
    lessons_learned: Mapped[str] = mapped_column(Text)
    strategy_adjustment: Mapped[str] = mapped_column(Text)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DailyReview(Base):
    __tablename__ = "daily_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_type: Mapped[str] = mapped_column(String(50), index=True)
    review_date: Mapped[str] = mapped_column(String(10), index=True)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_loss: Mapped[float] = mapped_column(Float, default=0.0)
    total_profit: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    patterns_found: Mapped[str] = mapped_column(Text, default="")
    conclusions: Mapped[str] = mapped_column(Text, default="")
    strategy_changes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IntelligenceItem(Base):
    __tablename__ = "intelligence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1000), default="")
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    symbols_mentioned: Mapped[str] = mapped_column(String(200), default="")
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class LearningInsight(Base):
    __tablename__ = "learning_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50))
    source_title: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    key_takeaways: Mapped[str] = mapped_column(Text)
    strategy_impact: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_type: Mapped[str] = mapped_column(String(50), unique=True)
    rsi_oversold: Mapped[float] = mapped_column(Float, default=30.0)
    rsi_overbought: Mapped[float] = mapped_column(Float, default=70.0)
    min_signal_score: Mapped[float] = mapped_column(Float, default=0.15)
    min_sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    stop_loss_pct: Mapped[float] = mapped_column(Float, default=0.02)
    take_profit_pct: Mapped[float] = mapped_column(Float, default=0.04)
    max_position_pct: Mapped[float] = mapped_column(Float, default=0.05)
    momentum_weight: Mapped[float] = mapped_column(Float, default=0.4)
    sentiment_weight: Mapped[float] = mapped_column(Float, default=0.3)
    technical_weight: Mapped[float] = mapped_column(Float, default=0.3)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BotState(Base):
    __tablename__ = "bot_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_type: Mapped[str] = mapped_column(String(50), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    last_action: Mapped[str] = mapped_column(String(200), default="")
    last_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    trades_today: Mapped[int] = mapped_column(Integer, default=0)
    pnl_today: Mapped[float] = mapped_column(Float, default=0.0)
    current_strategy_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
