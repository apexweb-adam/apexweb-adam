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

export type ApplyPendingInsightsResult = {
  status: string;
  pending_insights_applied: number;
  noise_insights_dismissed: number;
  timestamp: string;
};

export async function applyPendingInsights(): Promise<ApplyPendingInsightsResult> {
  const res = await fetch(`${DEFAULT_API}/learning/apply-pending-insights`, {
    method: "POST",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Apply insights failed: ${res.status}`);
  return res.json() as Promise<ApplyPendingInsightsResult>;
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

/** Full intelligence rows pushed over WebSocket in live updates. */
export type RecentIntelItem = IntelligenceItem;

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
  source_label?: string;
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

export type GraduationProgress = {
  trades_pct: number;
  win_rate_pct: number;
  profit_factor_pct: number;
  pnl_positive: boolean;
  overall_pct: number;
};

export type PerBotGateStatus = {
  paused: boolean;
  total_trades: number;
  win_rate: number;
  profit_factor: number | null;
  total_pnl: number;
  graduation_ready: boolean;
  graduation_blockers: string[];
  graduation_progress?: GraduationProgress;
  recommendation: string;
};

export type ScanPreviewSymbol = {
  symbol: string;
  price?: number;
  composite?: number;
  min_signal?: number;
  sentiment?: number;
  direction?: string;
  macd?: string;
  volume_ok?: boolean;
  would_enter?: boolean;
  blockers?: string[];
  recovery_ready?: boolean;
  monday_open_ready?: boolean;
  monday_gate_skip_ready?: boolean;
  verification_cooldown_bypass_ready?: boolean;
  verification_chronic_bypass_ready?: boolean;
  raw_signal?: number;
  integration_boost?: number;
  skip?: string;
};

export type ScanPreview = {
  bot_type: string;
  shadow_mode: boolean;
  graduation_nudge: boolean;
  commodities_verification_trade_count_nudge?: boolean;
  stocks_trade_count_nudge?: boolean;
  stocks_trade_count_gap?: number | null;
  stocks_gate_fast_scan_active?: boolean;
  stocks_open_imminent_scan?: boolean;
  stocks_trade_count_profit_lock_usd?: number;
  commodities_gate_fast_scan_active?: boolean;
  commodities_reopen_imminent_scan?: boolean;
  commodities_graduation_pf_profit_lock_usd?: number;
  crypto_chronic_loser_aligned_composite_floor?: number;
  crypto_strong_momentum_nudge?: boolean;
  crypto_pre_graduation_nudge?: boolean;
  crypto_cap_pressure_active?: boolean;
  crypto_momentum_retreat?: boolean;
  crypto_momentum_retreat_min_signal?: number;
  crypto_momentum_retreat_max_open?: number;
  crypto_momentum_retreat_min_raw_signal?: number;
  crypto_momentum_retreat_loss_wind_down_usd?: number;
  crypto_momentum_retreat_weak_signal_wind_down_max_upnl?: number;
  commodities_gate_loss_wind_down_usd?: number;
  crypto_shadow_raw_floor_active?: boolean;
  early_verification_boost?: boolean;
  shadow_bot_wr: number | null;
  proven_winners: string[];
  min_signal: number;
  open_count?: number;
  effective_open_cap?: number | null;
  cap_pressure_active?: boolean;
  shadow_open_cap?: number | null;
  held_symbols?: string[];
  open_ready_candidates?: string[];
  near_floor_candidates?: string[];
  recovery_candidates?: string[];
  session?: {
    in_session: boolean;
    mode: string;
    minutes_until_open?: number;
    minutes_until_close?: number | null;
  } | null;
  symbols: ScanPreviewSymbol[];
};

export type SessionPrepEntry = {
  bot_type: string;
  prep_active: boolean;
  prep_window_minutes: number;
  minutes_until_open: number | null;
  in_session?: boolean;
  extended_weekend_prep: boolean;
  nudge_active: boolean;
  nudge_label: string | null;
  session_mode: string | null;
  gate_fast_scan_active?: boolean;
  gate_reopen_imminent?: boolean;
  reopen_wake_active?: boolean;
  prep_phase?: "extended" | "imminent" | "wake" | "open";
  prep_scan_label?: string;
  minutes_until_imminent_scan?: number | null;
  minutes_until_wake?: number | null;
  imminent_scan_minutes?: number;
  open_ready_symbols?: string[];
  open_ready_details?: Array<{
    symbol: string;
    composite?: number;
    direction?: string;
    macd?: string;
    monday_gate_skip_ready?: boolean;
  verification_cooldown_bypass_ready?: boolean;
    blockers?: string[];
  }>;
  near_floor_symbols?: string[];
  near_floor_details?: Array<{
    symbol: string;
    composite?: number;
    direction?: string;
    macd?: string;
    blockers?: string[];
  }>;
  auto_entry_queued?: boolean;
  composite_floor?: number;
  open_count?: number;
  effective_open_cap?: number | null;
  cap_pressure_active?: boolean;
  trade_count_gap?: number | null;
};

export const SESSION_PREP_BOT_TYPES = ["stocks_futures", "commodities"] as const;
export type SessionPrepBotType = (typeof SESSION_PREP_BOT_TYPES)[number];

export type SessionPrepStatus = {
  stocks_futures: SessionPrepEntry;
  commodities: SessionPrepEntry;
  open_ready?: MondayRecoverySummary["open_ready"];
  open_ready_candidates?: string[];
  near_floor?: MondayRecoverySummary["open_ready"];
  near_floor_candidates?: string[];
  next_session_events?: NextSessionEvents;
  timestamp?: string;
  prep_cache_hit?: boolean;
  prep_cache_age_seconds?: number;
};

export function getSessionPrepEntry(
  sessionPrep: SessionPrepStatus | null | undefined,
  botType: string,
): SessionPrepEntry | undefined {
  if (!sessionPrep) return undefined;
  if (botType === "stocks_futures" || botType === "commodities") {
    return sessionPrep[botType];
  }
  return undefined;
}

export type OpenReadyDetail = {
  symbol: string;
  composite?: number;
  direction?: string;
  macd?: string;
  monday_gate_skip_ready?: boolean;
  verification_cooldown_bypass_ready?: boolean;
  blockers?: string[];
};

export type NextSessionEvent = {
  session_open_utc?: string | null;
  minutes_until_open?: number | null;
  reopen_imminent?: boolean;
  reopen_wake_active?: boolean;
  open_ready_symbols?: string[];
  open_ready_details?: OpenReadyDetail[];
  auto_gate_skip_at_open?: string[];
  auto_entry_queued?: boolean;
  prep_scan_label?: string;
  composite_floor?: number | null;
  near_floor_symbols?: string[];
  near_floor_details?: OpenReadyDetail[];
  prep_phase?: "extended" | "imminent" | "wake" | "open";
  minutes_until_imminent_scan?: number | null;
  minutes_until_wake?: number | null;
  imminent_scan_minutes?: number;
};

export type NextSessionEvents = {
  cme_reopen: NextSessionEvent;
  us_stocks_open: NextSessionEvent;
};

export type SessionOpenEvent = {
  timestamp: string;
  bot_type: string;
  event_type: string;
  symbols: string[];
  symbol_count?: number | null;
  detail?: string | null;
};

export type PlatformOutageEvent = {
  detected_at: string;
  last_online_utc?: string | null;
  gap_minutes: number;
  platform_revision?: string | null;
  stocks_in_session?: boolean;
  stocks_minutes_since_open?: number | null;
  cme_in_session?: boolean;
  us_open_ready_symbols?: string[];
  cme_open_ready_symbols?: string[];
  held_open_positions?: { bot_type: string; symbol: string }[];
};

export type SessionOpenChecklistSummary = {
  ready: boolean;
  phase?: string;
  prep_phase?: string;
  minutes_until_open?: number | null;
  open_ready_symbols: string[];
  near_floor_symbols?: string[];
  near_floor_gaps?: Record<string, number>;
  sticky_symbols?: string[];
  auto_entry_queued: boolean;
  composite_floor?: number | null;
  release_margin?: number | null;
  critical_failures: string[];
  has_burst_scan: boolean;
  has_auto_entry: boolean;
  platform_outage_recovery?: {
    window_active?: boolean;
    logged?: boolean;
    grace_minutes_remaining?: number | null;
    standard_grace_minutes?: number;
    extended_grace_minutes?: number;
  };
};

export type SessionOpenChecklists = {
  cme_reopen: SessionOpenChecklistSummary;
  us_stocks_open: SessionOpenChecklistSummary;
};

export type MondayRecoverySummary = {
  recovery_candidates: string[];
  open_ready_candidates?: string[];
  open_ready?: Array<{
    bot_type: string;
    symbol: string;
    composite?: number;
    blockers?: string[];
    minutes_until_open?: number | null;
    monday_gate_skip_ready?: boolean;
  verification_cooldown_bypass_ready?: boolean;
  }>;
  stocks_trade_count_nudge?: boolean;
  commodities_graduation_nudge?: boolean;
  commodities_verification_trade_count_nudge?: boolean;
  near_floor?: Array<{
    bot_type: string;
    symbol: string;
    composite?: number;
    blockers?: string[];
    minutes_until_open?: number | null;
  }>;
  near_floor_candidates?: string[];
  all: Array<{
    bot_type: string;
    symbol: string;
    composite?: number;
    blockers?: string[];
  }>;
  bots: Record<
    string,
    {
      recovery_candidates: string[];
      open_ready_candidates?: string[];
      session?: ScanPreview["session"];
      symbols: ScanPreviewSymbol[];
    }
  >;
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
  per_bot?: Record<string, PerBotGateStatus>;
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
  per_bot?: Record<string, PerBotGateStatus>;
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

export type ContentStudyHighlight = {
  source_type: string;
  source_label?: string;
  title: string;
  impact: string;
  confidence: number;
  applied: boolean;
};

export type ContentStudySummary = {
  insights_applied: number;
  recent: ContentStudyHighlight[];
};

export type IntelligenceSource = {
  source: string;
  status: string;
  items_collected: number;
  last_fetched: string | null;
  collection_mode?: string | null;
  synthetic_items_24h?: number | null;
  webhook_items_24h?: number | null;
  scoring_excludes_synthetic?: boolean | null;
  bearer_expires_at?: string | null;
  bearer_minutes_remaining?: number | null;
  bearer_polling_active?: boolean | null;
  oauth_configured?: boolean | null;
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
  backendHealth?: {
    reachable: boolean;
    suspended: boolean;
    reason?: "billing" | "unknown";
    message?: string;
    render_dashboard_url?: string;
    recovery_steps?: string[];
    platform_outage_grace_minutes_remaining?: number | null;
    platform_outage_grace_deadline_utc?: string | null;
    us_cash_session_catchup_minutes_remaining?: number | null;
    post_grace_catchup_active?: boolean;
    expected_platform_revision?: string;
    recovery_bots?: {
      bot_type: string;
      label: string;
      action: string;
      verify_script?: string;
      held_symbols?: string[];
    }[];
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
  platform_revision_current?: boolean | null;
  expected_platform_revision?: string | null;
  cme_deploy_urgency?: {
    active: boolean;
    minutes_until_open: number;
    message: string;
    deploy_command: string;
  } | null;
  cme_deploy_window?: {
    in_window: boolean;
    window_closed: boolean;
    minutes_until_open: number;
    minutes_until_window_opens: number;
    minutes_until_window_closes?: number | null;
    window_opens_at_utc?: string | null;
    window_closes_at_utc?: string | null;
    message: string;
    deploy_command: string;
    verify_command: string;
  } | null;
  deploy_credentials_ready?: boolean;
  deploy_credentials_warnings?: string[];
  deploy_credentials_nudges?: string[];
  dashboard_bundle_verify_command?: string;
  weekend_ops_verify_command?: string;
  crm_learning_verify_command?: string;
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
  max_stocks_open_positions?: number | null;
  blocked_new_entries?: string[];
  chronic_loser_symbols?: Record<string, string[]>;
  recent_loser_symbols?: Record<string, string[]>;
  proven_winner_symbols?: Record<string, string[]>;
  stocks_proven_winners_only?: boolean;
};

export type BotSessionInfo = {
  in_session: boolean;
  mode:
    | "entries"
    | "winddown"
    | "winddown_only"
    | "pre_session"
    | "outside_session"
    | "weekend_closed";
  session_open_utc?: string;
  session_close_utc?: string;
  minutes_until_open?: number;
  minutes_until_close?: number | null;
};

export type BotSessions = Record<string, BotSessionInfo>;

export type PlatformStatus = {
  platform: string;
  database: { engine: string; persistent: boolean };
  intelligence: {
    active_sources: number;
    total_sources: number;
    sources?: IntelligenceSource[];
  };
  scheduler?: Record<string, string>;
  bot_sessions?: BotSessions;
  gate_entry_tightening?: GateEntryTightening;
  integrations?: {
    tradingview_webhook?: boolean;
    tradingview_webhook_url?: string | null;
    tradingview_items?: number;
    tradingview_setup?: string | null;
    tradingview_test_endpoint?: string | null;
    tradingview_example_payload?: Record<string, string> | null;
    polymarket_market_scanner?: boolean;
    polymarket_account_hook?: boolean;
    polymarket_api_key?: boolean;
    polymarket_profile_url?: string | null;
    polymarket_intel_items?: number;
    polymarket_account_items?: number;
    polymarket_setup?: string | null;
    wallet_tracker?: boolean;
    wallet_tracker_webhook?: boolean;
    wallet_tracker_webhook_url?: string | null;
    wallet_tracker_example_payload?: Record<string, unknown> | null;
    fomo_family?: boolean;
    fomo_webhook?: boolean;
    fomo_webhook_url?: string | null;
    fomo_userscript_url?: string | null;
    fomo_bearer_configured?: boolean;
    fomo_bearer_polling_active?: boolean;
    fomo_bearer_expires_at?: string | null;
    fomo_bearer_minutes_remaining?: number | null;
    fomo_bearer_nudge_tier?: string | null;
    fomo_bearer_nudge_message?: string | null;
    fomo_bearer_refresh_hint?: string | null;
    fomo_webhook_fallback_active?: boolean;
    fomo_setup?: string | null;
    fomo_example_payload?: Record<string, unknown> | null;
    fomo_bridge_scripts?: {
      userscript?: string;
      zapier_guide?: string;
      manual_curl?: string;
      test_webhook?: string;
    };
    axiom_trade?: boolean;
    axiom_webhook?: boolean;
    axiom_webhook_url?: string | null;
    axiom_userscript_url?: string | null;
    axiom_session_configured?: boolean;
    axiom_session_polling_active?: boolean;
    axiom_poll_mode?: string | null;
    axiom_multi_wallet_ready?: boolean;
    axiom_tracked_wallets?: number;
    axiom_min_wallets?: number;
    axiom_setup?: string | null;
    axiom_example_payload?: Record<string, unknown> | null;
    phantom_wallet?: boolean;
    phantom_webhook?: boolean;
    phantom_webhook_url?: string | null;
    phantom_userscript_url?: string | null;
    phantom_portfolio_poll?: boolean;
    phantom_portfolio_poll_mode?: string | null;
    phantom_tracked_wallets?: number;
    phantom_setup?: string | null;
    phantom_example_payload?: Record<string, unknown> | null;
    reddit_oauth?: boolean;
    twitter_x?: boolean;
  };
  learning?: {
    trade_analyses: number;
    daily_reviews: number;
    insights_applied: number;
    insights_total: number;
    insights_pending?: number;
    intel_pattern_alerts?: string[];
    intel_pattern_count?: number;
  };
  content_study?: ContentStudySummary;
  profitability_gate?: ProfitabilityStatus;
  per_bot_gate?: Record<string, PerBotGateStatus>;
  session_prep?: SessionPrepStatus;
  open_ready_candidates?: string[];
  next_session_events?: NextSessionEvents;
  session_open_events?: SessionOpenEvent[];
  platform_outage_events?: PlatformOutageEvent[];
  session_open_checklists?: SessionOpenChecklists;
  deploy?: PlatformDeployStatus;
};
