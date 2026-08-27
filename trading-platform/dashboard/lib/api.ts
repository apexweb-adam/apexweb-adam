const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export async function fetchAPI<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${API_URL}/api${endpoint}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export function getWebSocketUrl(): string {
  return `${WS_URL}/api/ws`;
}

export type Stats = {
  total_equity: number;
  total_pnl: number;
  total_trades: number;
  avg_win_rate: number;
  open_positions: number;
  intelligence_items: number;
  mode: string;
  bots_active: number;
};

export type Portfolio = {
  bot_type: string;
  balance: number;
  equity: number;
  total_pnl: number;
  win_rate: number;
  total_trades: number;
  winning_trades: number;
};

export type Bot = {
  bot_type: string;
  status: string;
  last_action: string;
  last_scan_at: string | null;
  trades_today: number;
  pnl_today: number;
  strategy_version: number;
};

export type Trade = {
  id: number;
  bot_type: string;
  symbol: string;
  side: string;
  action: string;
  quantity: number;
  price: number;
  pnl: number;
  pnl_pct: number;
  is_winner: boolean | null;
  strategy: string;
  signal_score: number;
  sentiment_score: number;
  reason: string;
  executed_at: string;
};

export type Position = {
  id: number;
  bot_type: string;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  stop_loss: number;
  take_profit: number;
  opened_at: string;
};

export type IntelligenceItem = {
  id: number;
  source: string;
  category: string;
  title: string;
  content: string;
  url: string;
  sentiment: number;
  relevance_score: number;
  symbols_mentioned: string;
  fetched_at: string;
};

export type TradeAnalysis = {
  id: number;
  trade_id: number;
  bot_type: string;
  symbol: string;
  loss_amount: number;
  root_cause: string;
  market_context: string;
  lessons_learned: string;
  strategy_adjustment: string;
  analyzed_at: string;
};

export type DailyReview = {
  id: number;
  bot_type: string;
  review_date: string;
  total_trades: number;
  losing_trades: number;
  total_loss: number;
  total_profit: number;
  net_pnl: number;
  win_rate: number;
  patterns_found: string;
  conclusions: string;
  strategy_changes: string;
};

export type LearningInsight = {
  id: number;
  source_type: string;
  source_title: string;
  source_url: string;
  key_takeaways: string;
  strategy_impact: string;
  confidence: number;
  applied: boolean;
};

export type StrategyConfig = {
  bot_type: string;
  rsi_oversold: number;
  rsi_overbought: number;
  min_signal_score: number;
  min_sentiment_score: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  max_position_pct: number;
  version: number;
};
