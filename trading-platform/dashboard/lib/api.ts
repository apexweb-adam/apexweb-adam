import { PRODUCTION_BACKEND_WS } from "./production-backend";

const DEFAULT_API = "/api/backend";
const DEFAULT_WS = PRODUCTION_BACKEND_WS;

let wsUrlPromise: Promise<string> | null = null;

async function resolveWsUrl(): Promise<string> {
  if (typeof window === "undefined") {
    return process.env.NEXT_PUBLIC_WS_URL || DEFAULT_WS;
  }

  if (!wsUrlPromise) {
    wsUrlPromise = (async () => {
      try {
        const res = await fetch("/api/config", { cache: "no-store" });
        if (!res.ok) throw new Error("config fetch failed");
        const cfg = (await res.json()) as { wsUrl?: string };
        if (cfg.wsUrl) return `${cfg.wsUrl.replace(/\/$/, "")}/api/ws`;
      } catch {
        // fall through
      }
      const fallback = process.env.NEXT_PUBLIC_WS_URL || DEFAULT_WS;
      return `${fallback.replace(/\/$/, "")}/api/ws`;
    })();
  }

  return wsUrlPromise;
}

export async function fetchAPI<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${DEFAULT_API}${endpoint}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export function getWebSocketUrl(): string {
  // Sync fallback for SSR; client reconnects after config loads.
  const fallback = process.env.NEXT_PUBLIC_WS_URL || DEFAULT_WS;
  return `${fallback.replace(/\/$/, "")}/api/ws`;
}

export async function getWebSocketUrlAsync(): Promise<string> {
  return resolveWsUrl();
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

/** Subset pushed over WebSocket in live updates. */
export type RecentIntelItem = Pick<
  IntelligenceItem,
  "id" | "source" | "category" | "title" | "sentiment" | "relevance_score" | "fetched_at"
>;

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

export type EquityHistoryPoint = {
  date: string;
  daily_pnl: number;
  cumulative_pnl: number;
};

export type ProfitabilityStatus = {
  live_trading_ready: boolean;
  paper_trading_only: boolean;
  paused_bots?: string[];
  total_trades: number;
  win_rate: number;
  profit_factor: number | null;
  total_pnl: number;
  days_trading?: number;
  verification_day?: number;
  verification_days_remaining?: number;
  verification_started_at?: string | null;
  recommendation: string;
  checks: Record<string, { required: unknown; actual: unknown; passed: boolean }>;
  aggregate?: {
    total_trades: number;
    win_rate: number;
    profit_factor: number | null;
    total_pnl: number;
  };
  equity_history?: EquityHistoryPoint[];
};

/** Backend /api/active-gate shape (via /api/backend/active-gate proxy). */
export type ActiveGateStatus = {
  paused_bots?: string[];
  active_bots: {
    total_trades: number;
    win_rate: number;
    profit_factor: number | null;
    total_pnl: number;
  };
  aggregate?: ProfitabilityStatus["aggregate"];
  verification_day?: number;
  verification_days_remaining?: number;
  live_trading_ready?: boolean;
  checks: ProfitabilityStatus["checks"];
  recommendation: string;
};

export type VerificationSnapshot = {
  snapshot_date: string;
  verification_day: number;
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  total_pnl: number;
  performance_checks_passed: boolean;
  live_trading_ready: boolean;
  created_at: string | null;
};

export type IntelligenceSource = {
  source: string;
  status: string;
  items_collected: number;
  last_fetched: string | null;
};

export type IntelRouting = {
  bot_source_weights: Record<string, Record<string, number>>;
  political_event_types: { type: string; assets: string[]; bots: string[] }[];
};

export type DashboardConfig = {
  apiUrl: string;
  wsUrl: string;
  mode: string;
  bundleRevision?: string;
  features?: {
    activeGate?: boolean;
    clientGateEnrichment?: boolean;
    proxyGateEnrichment?: boolean;
  };
  githubMainCommit?: string | null;
  promoteUrl?: string;
};

export type PlatformDeployStatus = {
  database_persistent: boolean;
  intelligence_complete: boolean;
  env_configured: Record<string, boolean>;
  render_blueprint: string;
  supabase_project: string;
  dashboard_url: string;
  verified_dashboard_url?: string;
  vercel_bundle_stale?: boolean;
  vercel_bundle_revision?: string | null;
  vercel_promote_deployment_id?: string;
  vercel_promote_url?: string;
  platform_revision?: string | null;
  git_commit?: string | null;
  latest_main_commit?: string | null;
  latest_main_message?: string | null;
  is_stale?: boolean;
  stale_minutes?: number | null;
  commits_behind?: number;
  pending_changes?: { sha: string; message: string }[];
  next_steps: string[];
};

export type GateEntryTightening = {
  active: boolean;
  win_rate: number;
  min_sentiment: number;
  require_macd_bullish: boolean;
  min_composite_boost: number;
  max_pm_open_positions: number | null;
  max_crypto_open_positions?: number | null;
  max_commodities_open_positions?: number | null;
  blocked_new_entries?: string[];
  chronic_loser_symbols?: Record<string, string[]>;
  proven_winner_symbols?: Record<string, string[]>;
};

export type PlatformStatus = {
  platform: string;
  database: { engine: string; persistent: boolean };
  intelligence: { active_sources: number; total_sources: number };
  scheduler?: Record<string, string>;
  gate_entry_tightening?: GateEntryTightening;
  integrations?: {
    tradingview_webhook?: boolean;
    tradingview_webhook_url?: string | null;
    tradingview_items?: number;
    tradingview_setup?: string | null;
    tradingview_test_endpoint?: string | null;
    tradingview_example_payload?: Record<string, string> | null;
  };
  learning?: {
    trade_analyses: number;
    daily_reviews: number;
    insights_applied: number;
    insights_total: number;
  };
  deploy?: PlatformDeployStatus;
};
