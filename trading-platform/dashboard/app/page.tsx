"use client";

import {
  Activity,
  BarChart3,
  Bot,
  Brain,
  Circle,
  DollarSign,
  LineChart,
  Newspaper,
  Settings,
  Shield,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import { useState, useMemo, useEffect } from "react";
import { useLiveData } from "@/lib/useLiveData";
import { useAPI } from "@/lib/useAPI";
import { fetchAPI } from "@/lib/api";
import {
  VERIFIED_PREVIEW_URL,
  VERIFIED_PROMOTE_DEPLOYMENT_ID,
} from "@/lib/deploy-health";
import {
  botLabel,
  cn,
  formatCurrency,
  formatPct,
  formatTime,
  pnlColor,
  sentimentColor,
} from "@/lib/utils";
import type {
  Trade,
  Position,
  IntelligenceItem,
  TradeAnalysis,
  DailyReview,
  LearningInsight,
  ScanPreview,
  MondayRecoverySummary,
  SessionPrepStatus,
  SessionPrepEntry,
  StrategyConfig,
  ProfitabilityStatus,
  VerificationSnapshot,
  IntelligenceSource,
  PlatformStatus,
  DashboardConfig,
  IntelRouting,
  ActiveGateStatus,
  EquityHistoryPoint,
  BotSessions,
} from "@/lib/api";
import { enrichProfitabilityStatus, activeGateToProfitability, buildEquityHistoryFromTrades } from "@/lib/profitability";
import { VerificationPnLChart } from "@/components/VerificationPnLChart";
import { IntelRoutingPanel } from "@/components/IntelRoutingPanel";

type Tab = "overview" | "trades" | "positions" | "intelligence" | "learning" | "strategy";

export default function Dashboard() {
  const { stats, portfolios, bots, positions: livePositions, trades: liveTrades, recentIntel, analyses: liveAnalyses, reviews: liveReviews, insights: liveInsights, strategies: liveStrategies, intelSources: liveIntelSources, verificationHistory: liveVerificationHistory, connected, lastUpdate, lastTrade, profitabilityGate: liveProfitability, gateEntryTightening, botSessions, mondayRecovery, sessionPrep, contentStudy } = useLiveData();
  const { data: tradesRest } = useAPI<Trade[]>("/trades?limit=50", 30000);
  const { data: gateTradesRest } = useAPI<Trade[]>("/trades?limit=200", 30000);
  const { data: positionsRest } = useAPI<Position[]>("/positions", 30000);
  const trades = connected ? liveTrades : (tradesRest ?? []);
  const positions = connected ? livePositions : (positionsRest ?? []);
  const { data: intelligence } = useAPI<IntelligenceItem[]>("/intelligence?limit=30", 15000);
  const { data: analysesRest } = useAPI<TradeAnalysis[]>("/analyses?limit=20", 15000);
  const { data: reviewsRest } = useAPI<DailyReview[]>("/reviews?limit=10", 30000);
  const { data: insightsRest } = useAPI<LearningInsight[]>("/insights?limit=20", 30000);
  const { data: strategiesRest } = useAPI<StrategyConfig[]>("/strategies", 30000);
  const { data: intelSourcesRest } = useAPI<IntelligenceSource[]>("/intelligence/sources", 30000);
  const analyses = liveAnalyses.length > 0 ? liveAnalyses : (analysesRest ?? []);
  const reviews = liveReviews.length > 0 ? liveReviews : (reviewsRest ?? []);
  const insights = liveInsights.length > 0 ? liveInsights : (insightsRest ?? []);
  const strategies = liveStrategies.length > 0 ? liveStrategies : (strategiesRest ?? []);
  const intelSources = liveIntelSources.length > 0 ? liveIntelSources : (intelSourcesRest ?? []);
  const { data: verificationHistoryRest } = useAPI<VerificationSnapshot[]>(
    "/verification/history?limit=30",
    60000
  );
  const verificationHistory =
    liveVerificationHistory.length > 0
      ? liveVerificationHistory
      : (verificationHistoryRest ?? []);
  const { data: profitability } = useAPI<ProfitabilityStatus>("/profitability", 15000);
  const { data: activeGate } = useAPI<ActiveGateStatus>("/active-gate", 15000);
  const { data: equityHistory } = useAPI<EquityHistoryPoint[]>("/equity-history", 60000);
  const { data: intelRouting } = useAPI<IntelRouting>("/intelligence/routing", 60000);
  const { data: platformStatus } = useAPI<PlatformStatus>("/status", 30000);
  const [tab, setTab] = useState<Tab>("overview");
  const [dashConfig, setDashConfig] = useState<DashboardConfig | null>(null);

  useEffect(() => {
    fetch("/api/config", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((cfg) => setDashConfig(cfg))
      .catch(() => setDashConfig(null));
  }, []);

  const vercelFullBundle = dashConfig?.features?.activeGate === true;
  const vercelProxyMode = dashConfig != null && !vercelFullBundle;
  const gateViaProxy = Boolean(activeGate?.active_bots);
  const vercelStale = vercelProxyMode;

  const intelFeed = useMemo(() => {
    const rest = intelligence ?? [];
    if (!connected || recentIntel.length === 0) return rest;
    const byId = new Map<number, IntelligenceItem>();
    for (const item of rest) byId.set(item.id, item);
    for (const item of recentIntel) {
      byId.set(item.id, {
        ...item,
        content: item.content || item.title,
        url: item.url || "",
        symbols_mentioned: item.symbols_mentioned || "",
      });
    }
    return Array.from(byId.values()).sort(
      (a, b) => new Date(b.fetched_at).getTime() - new Date(a.fetched_at).getTime()
    );
  }, [intelligence, recentIntel, connected]);

  const gateTrades = useMemo(() => {
    const rest = gateTradesRest ?? tradesRest ?? [];
    if (!connected || liveTrades.length === 0) return rest;
    const byId = new Map<number, Trade>();
    for (const t of rest) byId.set(t.id, t);
    for (const t of liveTrades) byId.set(t.id, t);
    return Array.from(byId.values());
  }, [connected, liveTrades, gateTradesRest, tradesRest]);

  const equityHistoryFromTrades = useMemo(
    () => buildEquityHistoryFromTrades(gateTrades.filter((t) => t.action === "sell")),
    [gateTrades]
  );
  const chartEquityHistory = useMemo(() => {
    if (connected && (liveProfitability?.equity_history?.length ?? 0) > 0) {
      return liveProfitability!.equity_history!;
    }
    if ((equityHistory?.length ?? 0) > 0) return equityHistory!;
    if ((profitability?.equity_history?.length ?? 0) > 0) return profitability!.equity_history!;
    return equityHistoryFromTrades;
  }, [connected, liveProfitability, equityHistory, profitability, equityHistoryFromTrades]);

  const gateStatus = useMemo(() => {
    const profSource = connected && liveProfitability ? liveProfitability : profitability;
    if (activeGate?.active_bots) {
      const merged = activeGateToProfitability(activeGate, profSource ?? undefined);
      if (!merged.per_bot && profSource?.per_bot) {
        merged.per_bot = profSource.per_bot;
      }
      return merged;
    }
    return enrichProfitabilityStatus(
      profSource ?? undefined,
      gateTrades,
      portfolios,
      strategies
    );
  }, [activeGate, liveProfitability, connected, profitability, gateTrades, portfolios, strategies]);

  const liveGateTightening =
    gateEntryTightening ?? platformStatus?.gate_entry_tightening;

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "overview", label: "Overview", icon: <BarChart3 size={16} /> },
    { id: "trades", label: "Trades", icon: <Activity size={16} /> },
    { id: "positions", label: "Positions", icon: <LineChart size={16} /> },
    { id: "intelligence", label: "Intelligence", icon: <Newspaper size={16} /> },
    { id: "learning", label: "Learning", icon: <Brain size={16} /> },
    { id: "strategy", label: "Strategy", icon: <Settings size={16} /> },
  ];

  return (
    <div className="min-h-screen bg-apex-dark">
      <header className="border-b border-apex-border bg-apex-card/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-apex-gold to-apex-purple flex items-center justify-center">
              <Zap className="text-apex-dark" size={20} />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">Apex Trading Platform</h1>
              <p className="text-xs text-gray-500">Multi-Market Paper Trading CRM</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-apex-green/10 border border-apex-green/20">
              <Shield size={14} className="text-apex-green" />
              <span className="text-xs text-apex-green font-medium">PAPER TRADING</span>
            </div>
            <div className="flex items-center gap-2">
              <Circle
                size={8}
                className={cn("fill-current", connected ? "text-apex-green" : "text-apex-red")}
              />
              <span className="text-xs text-gray-400">
                {connected ? "Live" : "Reconnecting..."}
              </span>
            </div>
            {lastTrade && (
              <span className="text-xs text-apex-gold animate-pulse">
                {String(lastTrade.action ?? "trade").toUpperCase()} {String(lastTrade.symbol ?? "")}
              </span>
            )}
            {lastUpdate && (
              <span className="text-xs text-gray-600">Updated {formatTime(lastUpdate)}</span>
            )}
          </div>
        </div>
      </header>

      {vercelStale && (
        <div className="bg-apex-gold/15 border-b border-apex-gold/30 px-6 py-2">
          <p className="max-w-[1600px] mx-auto text-xs text-apex-gold">
            {gateViaProxy
              ? "Production CRM is operational via backend proxy — gate metrics and trades load correctly."
              : "Dashboard bundle is stale — promote latest main in Vercel for native /api/active-gate."}{" "}
            {!gateViaProxy && "Gate metrics still load via backend proxy when available. "}
            Promote for native routes and newest UI.{" "}
            <a
              href={dashConfig?.promoteUrl ?? "https://vercel.com/apexweb-adams-projects/apex-trading-dashboard/deployments"}
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-white"
            >
              Promote in Vercel →
            </a>
            {(platformStatus?.deploy?.verified_dashboard_url || VERIFIED_PREVIEW_URL) && (
              <>
                {" "}
                <a
                  href={platformStatus?.deploy?.verified_dashboard_url ?? VERIFIED_PREVIEW_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-white"
                >
                  Open verified preview →
                </a>
              </>
            )}
            {dashConfig?.githubMainCommit && (
              <span className="ml-2 font-mono text-[10px] text-gray-500">
                main {dashConfig.githubMainCommit}
              </span>
            )}
          </p>
        </div>
      )}

      <div className="max-w-[1600px] mx-auto px-6 py-6">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-6">
          <StatCard
            label="Total Equity"
            value={formatCurrency(stats?.total_equity ?? 0)}
            icon={<DollarSign size={18} className="text-apex-gold" />}
          />
          <StatCard
            label="Total P&L"
            value={formatCurrency(stats?.total_pnl ?? 0)}
            valueClass={pnlColor(stats?.total_pnl ?? 0)}
            icon={
              (stats?.total_pnl ?? 0) >= 0 ? (
                <TrendingUp size={18} className="text-apex-green" />
              ) : (
                <TrendingDown size={18} className="text-apex-red" />
              )
            }
          />
          <StatCard
            label="Win Rate"
            value={formatPct(gateStatus?.win_rate ?? stats?.avg_win_rate ?? 0)}
            icon={<BarChart3 size={18} className="text-apex-blue" />}
          />
          <StatCard
            label="Total Trades"
            value={String(stats?.total_trades ?? 0)}
            icon={<Activity size={18} className="text-apex-purple" />}
          />
          <StatCard
            label="Open Positions"
            value={String(stats?.open_positions ?? 0)}
            icon={<LineChart size={18} className="text-apex-gold" />}
          />
          <StatCard
            label="Intel Items"
            value={String(stats?.intelligence_items ?? 0)}
            icon={<Newspaper size={18} className="text-apex-blue" />}
          />
        </div>

        <div className="flex gap-2 mb-6 overflow-x-auto pb-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap",
                tab === t.id
                  ? "bg-apex-gold/10 text-apex-gold border border-apex-gold/30"
                  : "bg-apex-card text-gray-400 border border-apex-border hover:text-white"
              )}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        {tab === "overview" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <MondayRecoveryBanner summary={mondayRecovery} />
              <SessionPrepBanner sessionPrep={sessionPrep} />
              <Card title="Bot Status">
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                  {bots.map((bot) => (
                    <BotCard
                      key={bot.bot_type}
                      bot={bot}
                      sessionPrep={sessionPrep?.[bot.bot_type as keyof SessionPrepStatus]}
                      session={
                        botSessions?.[bot.bot_type] ??
                        platformStatus?.bot_sessions?.[bot.bot_type]
                      }
                      gate={{
                        ...(liveGateTightening?.active
                          ? {
                              blocked: liveGateTightening.blocked_new_entries?.includes(
                                bot.bot_type
                              ),
                              provenWinners:
                                liveGateTightening.proven_winner_symbols?.[bot.bot_type],
                            }
                          : {}),
                        graduation: gateStatus?.per_bot?.[bot.bot_type],
                      }}
                    />
                  ))}
                  {bots.length === 0 &&
                    ["crypto", "stocks_futures", "commodities", "polymarket"].map((type) => (
                      <BotCard
                        key={type}
                        bot={{
                          bot_type: type,
                          status: "starting",
                          last_action: "Initializing...",
                          last_scan_at: null,
                          trades_today: 0,
                          pnl_today: 0,
                          strategy_version: 1,
                        }}
                      />
                    ))}
                </div>
              </Card>
              <Card title="Recent Trades">
                <TradesTable trades={(trades ?? []).slice(0, 10)} compact />
              </Card>
            </div>
            <div className="space-y-6">
              {platformStatus?.scheduler && (
                <Card title="Autonomous Operations">
                  <div className="space-y-2">
                    {Object.entries(platformStatus.scheduler).map(([key, value]) => (
                      <div key={key} className="flex justify-between text-xs">
                        <span className="text-gray-500">{key.replace(/_/g, " ")}</span>
                        <span className="text-apex-green font-medium">{value}</span>
                      </div>
                    ))}
                  </div>
                  {platformStatus.learning && (
                    <div className="mt-4 pt-4 border-t border-apex-border space-y-1 text-xs text-gray-500">
                      <p>
                        Learning: {platformStatus.learning.trade_analyses} post-mortems ·{" "}
                        {platformStatus.learning.daily_reviews} daily reviews ·{" "}
                        {platformStatus.learning.insights_applied}/{platformStatus.learning.insights_total}{" "}
                        insights applied
                        {(platformStatus.learning.insights_pending ?? 0) > 0 && (
                          <span className="text-apex-gold">
                            {" "}
                            · {platformStatus.learning.insights_pending} pending
                          </span>
                        )}
                      </p>
                    </div>
                  )}
                </Card>
              )}
              {(vercelStale ||
                (platformStatus?.deploy &&
                  (platformStatus.deploy.is_stale ||
                    (platformStatus.deploy.next_steps?.length ?? 0) > 0))) && (
                <Card title="Production Deploy">
                  <div className="space-y-3">
                    {vercelStale && (
                      <div className="rounded-lg border border-apex-gold/40 bg-apex-gold/10 px-3 py-2 text-xs text-apex-gold">
                        Vercel dashboard bundle stale — promote{" "}
                        {platformStatus?.deploy?.vercel_promote_deployment_id ??
                          VERIFIED_PROMOTE_DEPLOYMENT_ID}{" "}
                        for full features. Active-bot gate works via /api/backend/active-gate proxy.{" "}
                        <a
                          href={
                            platformStatus?.deploy?.verified_dashboard_url ?? VERIFIED_PREVIEW_URL
                          }
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline hover:text-white"
                        >
                          Use verified preview →
                        </a>
                      </div>
                    )}
                    {platformStatus?.deploy?.is_stale && (
                      <div className="rounded-lg border border-apex-gold/40 bg-apex-gold/10 px-3 py-2 text-xs text-apex-gold">
                        Backend deploy is stale
                        {platformStatus.deploy.stale_minutes != null && (
                          <span> ({platformStatus.deploy.stale_minutes}m behind main)</span>
                        )}
                        {platformStatus.deploy.git_commit && platformStatus.deploy.latest_main_commit && (
                          <div className="mt-1 font-mono text-[10px] text-gray-400">
                            running {platformStatus.deploy.git_commit.slice(0, 12)} → main{" "}
                            {platformStatus.deploy.latest_main_commit.slice(0, 12)}
                          </div>
                        )}
                        {(platformStatus.deploy.pending_changes?.length ?? 0) > 0 && (
                          <ul className="mt-2 space-y-1 text-[10px] text-gray-400 list-disc list-inside">
                            {platformStatus.deploy.pending_changes!.slice(0, 4).map((c) => (
                              <li key={c.sha}>{c.message}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
                    {platformStatus?.deploy && (
                      <>
                        <div className="flex flex-wrap gap-2 text-xs">
                          <span
                            className={cn(
                              "px-2 py-1 rounded-full",
                              platformStatus.database.persistent
                                ? "bg-apex-green/10 text-apex-green"
                                : "bg-apex-gold/10 text-apex-gold"
                            )}
                          >
                            DB: {platformStatus.database.engine}
                          </span>
                          <span className="px-2 py-1 rounded-full bg-apex-green/10 text-apex-green">
                            Intel {platformStatus.intelligence.active_sources}/
                            {platformStatus.intelligence.total_sources}
                          </span>
                          {platformStatus.deploy.platform_revision && (
                            <span className="px-2 py-1 rounded-full bg-gray-800 text-gray-400 font-mono">
                              rev {platformStatus.deploy.platform_revision}
                            </span>
                          )}
                        </div>
                        {(platformStatus.integrations?.tradingview_webhook ||
                          platformStatus.integrations?.tradingview_setup) && (
                          <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
                            <p className="text-apex-gold font-medium mb-1">TradingView webhook ready</p>
                            {platformStatus.integrations.tradingview_setup && (
                              <p>{platformStatus.integrations.tradingview_setup}</p>
                            )}
                            {platformStatus.integrations.tradingview_webhook_url && (
                              <p className="mt-1 font-mono text-[10px] text-gray-500 break-all">
                                {platformStatus.integrations.tradingview_webhook_url}
                              </p>
                            )}
                            {platformStatus.integrations.tradingview_test_endpoint && (
                              <p className="mt-2 text-[10px] text-gray-500">
                                Test: {platformStatus.integrations.tradingview_test_endpoint}
                              </p>
                            )}
                            {platformStatus.integrations.tradingview_items != null &&
                              platformStatus.integrations.tradingview_items > 0 && (
                                <p className="mt-1 text-apex-green text-[10px]">
                                  {platformStatus.integrations.tradingview_items} alert(s) received
                                </p>
                              )}
                            {platformStatus.integrations.tradingview_example_payload && (
                              <pre className="mt-2 p-2 rounded bg-black/40 text-[10px] text-gray-400 overflow-x-auto">
                                {JSON.stringify(
                                  platformStatus.integrations.tradingview_example_payload,
                                  null,
                                  2
                                )}
                              </pre>
                            )}
                          </div>
                        )}
                        {(platformStatus.integrations?.wallet_tracker_webhook ||
                          platformStatus.integrations?.wallet_tracker) && (
                          <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
                            <p className="text-apex-gold font-medium mb-1">
                              Wallet tracker {platformStatus.integrations.wallet_tracker ? "active" : "webhook ready"}
                            </p>
                            {platformStatus.integrations.wallet_tracker_webhook_url && (
                              <p className="font-mono text-[10px] text-gray-500 break-all">
                                {platformStatus.integrations.wallet_tracker_webhook_url}
                              </p>
                            )}
                            <p className="mt-1 text-[10px] text-gray-500">
                              On-chain whale scan + external monitor ingest (Arkham, Nansen, custom)
                            </p>
                            {platformStatus.integrations.wallet_tracker_example_payload && (
                              <pre className="mt-2 p-2 rounded bg-black/40 text-[10px] text-gray-400 overflow-x-auto">
                                {JSON.stringify(
                                  platformStatus.integrations.wallet_tracker_example_payload,
                                  null,
                                  2
                                )}
                              </pre>
                            )}
                          </div>
                        )}
                        {(platformStatus.integrations?.fomo_webhook ||
                          platformStatus.integrations?.fomo_family) && (
                          <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
                            <p className="text-apex-gold font-medium mb-1">
                              fomo.family {platformStatus.integrations.fomo_webhook ? "webhook ready" : "enabled"}
                            </p>
                            {platformStatus.integrations.fomo_webhook_url && (
                              <p className="font-mono text-[10px] text-gray-500 break-all">
                                {platformStatus.integrations.fomo_webhook_url}
                              </p>
                            )}
                            {platformStatus.integrations.fomo_userscript_url && (
                              <p className="mt-1 text-[10px]">
                                <a
                                  href={platformStatus.integrations.fomo_userscript_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-apex-gold hover:underline break-all"
                                >
                                  Install userscript (Tampermonkey v1.1 — auto-syncs bearer)
                                </a>
                              </p>
                            )}
                            {platformStatus.integrations.fomo_bearer_configured && (
                              <p
                                className={cn(
                                  "mt-1 text-[10px]",
                                  platformStatus.integrations.fomo_bearer_polling_active
                                    ? "text-green-400"
                                    : "text-amber-400"
                                )}
                              >
                                Server poll:{" "}
                                {platformStatus.integrations.fomo_bearer_polling_active
                                  ? `active (${platformStatus.integrations.fomo_bearer_minutes_remaining ?? "?"} min left)`
                                  : "bearer expired — keep fomo.family open in Tampermonkey or refresh token"}
                              </p>
                            )}
                            {platformStatus.integrations.fomo_webhook_fallback_active && (
                              <p className="mt-1 text-[10px] text-blue-400">
                                Webhook fallback active — Tampermonkey bridge still ingests trades
                              </p>
                            )}
                            {platformStatus.integrations.fomo_setup && (
                              <p className="mt-1 text-[10px] text-gray-500">
                                {platformStatus.integrations.fomo_setup}
                              </p>
                            )}
                            {platformStatus.integrations.fomo_bridge_scripts && (
                              <ul className="mt-2 text-[10px] text-gray-500 list-disc list-inside space-y-1">
                                <li>
                                  Userscript:{" "}
                                  <code>{platformStatus.integrations.fomo_bridge_scripts.userscript}</code>
                                </li>
                                <li>
                                  Zapier:{" "}
                                  <code>{platformStatus.integrations.fomo_bridge_scripts.zapier_guide}</code>
                                </li>
                                <li>
                                  Manual curl:{" "}
                                  <code>{platformStatus.integrations.fomo_bridge_scripts.manual_curl}</code>
                                </li>
                              </ul>
                            )}
                            {platformStatus.integrations.fomo_example_payload && (
                              <pre className="mt-2 p-2 rounded bg-black/40 text-[10px] text-gray-400 overflow-x-auto">
                                {JSON.stringify(
                                  platformStatus.integrations.fomo_example_payload,
                                  null,
                                  2
                                )}
                              </pre>
                            )}
                          </div>
                        )}
                        {(platformStatus.integrations?.axiom_webhook ||
                          platformStatus.integrations?.axiom_trade) && (
                          <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
                            <p className="text-apex-gold font-medium mb-1">
                              axiom.trade{" "}
                              {platformStatus.integrations.axiom_multi_wallet_ready
                                ? `multi-wallet (${platformStatus.integrations.axiom_tracked_wallets ?? 8}+)`
                                : platformStatus.integrations.axiom_webhook
                                  ? "webhook ready"
                                  : "enabled"}
                            </p>
                            {platformStatus.integrations.axiom_webhook_url && (
                              <p className="font-mono text-[10px] text-gray-500 break-all">
                                {platformStatus.integrations.axiom_webhook_url}
                              </p>
                            )}
                            {platformStatus.integrations.axiom_userscript_url && (
                              <p className="mt-1 text-[10px]">
                                <a
                                  href={platformStatus.integrations.axiom_userscript_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-apex-gold hover:underline break-all"
                                >
                                  Install axiom userscript (24/7 memecoin + wallet bridge)
                                </a>
                              </p>
                            )}
                            {platformStatus.integrations.axiom_trade && (
                              <p className="mt-1 text-[10px] text-gray-400">
                                Poll mode:{" "}
                                <span
                                  className={cn(
                                    platformStatus.integrations.axiom_poll_mode === "session"
                                      ? "text-green-400"
                                      : platformStatus.integrations.axiom_poll_mode === "mirror"
                                        ? "text-blue-400"
                                        : "text-amber-400"
                                  )}
                                >
                                  {platformStatus.integrations.axiom_poll_mode ?? "off"}
                                </span>
                                {platformStatus.integrations.axiom_poll_mode === "mirror"
                                  ? " — mirroring wallet_tracker + phantom holdings"
                                  : ""}
                              </p>
                            )}
                            {platformStatus.integrations.axiom_session_configured && (
                              <p
                                className={cn(
                                  "mt-1 text-[10px]",
                                  platformStatus.integrations.axiom_session_polling_active
                                    ? "text-green-400"
                                    : "text-amber-400"
                                )}
                              >
                                Session poll:{" "}
                                {platformStatus.integrations.axiom_session_polling_active
                                  ? "active"
                                  : "expired — keep axiom.trade open in Tampermonkey"}
                              </p>
                            )}
                            {platformStatus.integrations.axiom_setup && (
                              <p className="mt-1 text-[10px] text-gray-500">
                                {platformStatus.integrations.axiom_setup}
                              </p>
                            )}
                            {platformStatus.integrations.axiom_example_payload && (
                              <pre className="mt-2 p-2 rounded bg-black/40 text-[10px] text-gray-400 overflow-x-auto">
                                {JSON.stringify(
                                  platformStatus.integrations.axiom_example_payload,
                                  null,
                                  2
                                )}
                              </pre>
                            )}
                          </div>
                        )}
                        {(platformStatus.integrations?.phantom_webhook ||
                          platformStatus.integrations?.phantom_wallet) && (
                          <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
                            <p className="text-apex-gold font-medium mb-1">
                              Phantom wallet{" "}
                              {platformStatus.integrations.phantom_webhook ? "webhook ready" : "enabled"}
                            </p>
                            {platformStatus.integrations.phantom_webhook_url && (
                              <p className="font-mono text-[10px] text-gray-500 break-all">
                                {platformStatus.integrations.phantom_webhook_url}
                              </p>
                            )}
                            {platformStatus.integrations.phantom_userscript_url && (
                              <p className="mt-1 text-[10px]">
                                <a
                                  href={platformStatus.integrations.phantom_userscript_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-apex-gold hover:underline break-all"
                                >
                                  Install Phantom userscript (portfolio forwarding)
                                </a>
                              </p>
                            )}
                            {platformStatus.integrations.phantom_portfolio_poll ? (
                              <p className="mt-1 text-[10px] text-green-400">
                                Server portfolio poll active
                                {platformStatus.integrations.phantom_portfolio_poll_mode
                                  ? ` (${platformStatus.integrations.phantom_portfolio_poll_mode})`
                                  : ""}
                                {platformStatus.integrations.phantom_tracked_wallets
                                  ? ` — ${platformStatus.integrations.phantom_tracked_wallets} wallets`
                                  : ""}
                              </p>
                            ) : (
                              <p className="mt-1 text-[10px] text-amber-400">
                                Portfolio poll inactive
                                {platformStatus.integrations.phantom_portfolio_poll_mode
                                  ? ` (${platformStatus.integrations.phantom_portfolio_poll_mode})`
                                  : ""}
                                {" — "}
                                set HELIUS_API_KEY or install Phantom userscript
                              </p>
                            )}
                            {platformStatus.integrations.phantom_setup && (
                              <p className="mt-1 text-[10px] text-gray-500">
                                {platformStatus.integrations.phantom_setup}
                              </p>
                            )}
                            {platformStatus.integrations.phantom_example_payload && (
                              <pre className="mt-2 p-2 rounded bg-black/40 text-[10px] text-gray-400 overflow-x-auto">
                                {JSON.stringify(
                                  platformStatus.integrations.phantom_example_payload,
                                  null,
                                  2
                                )}
                              </pre>
                            )}
                          </div>
                        )}
                        {(platformStatus.deploy.next_steps?.length ?? 0) > 0 && (
                          <ul className="space-y-2 text-xs text-gray-400 list-disc list-inside">
                            {platformStatus.deploy.next_steps.map((step) => (
                              <li key={step}>{step}</li>
                            ))}
                          </ul>
                        )}
                        <a
                          href={platformStatus.deploy.render_blueprint}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-block text-xs text-apex-gold hover:underline"
                        >
                          Open Render Blueprint →
                        </a>
                      </>
                    )}
                  </div>
                </Card>
              )}
              <Card title="Profitability Gate">
                {gateStatus ? (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-400">Live trading ready</span>
                      <span
                        className={cn(
                          "text-xs px-2 py-1 rounded-full font-medium",
                          gateStatus.live_trading_ready
                            ? "bg-apex-green/10 text-apex-green"
                            : "bg-apex-gold/10 text-apex-gold"
                        )}
                      >
                        {gateStatus.live_trading_ready ? "READY" : "PAPER ONLY"}
                      </span>
                    </div>
                    {gateStatus.verification_started_at && (
                      <p className="text-xs text-gray-500">
                        Verification day {gateStatus.verification_day ?? (gateStatus.days_trading ?? 0) + 1} of 30
                        {gateStatus.verification_days_remaining != null && (
                          <span className="text-gray-600">
                            {" "}
                            · {gateStatus.verification_days_remaining} days remaining
                          </span>
                        )}
                        <span className="text-gray-600">
                          {" "}
                          · started{" "}
                          {new Date(gateStatus.verification_started_at).toLocaleDateString()}
                        </span>
                      </p>
                    )}
                    {gateStatus.verification_day != null && (
                      <div className="space-y-1">
                        <div className="flex justify-between text-[10px] text-gray-500 uppercase tracking-wide">
                          <span>Verification period</span>
                          <span>{Math.min(30, gateStatus.verification_day)}/30 days</span>
                        </div>
                        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-apex-gold/80 rounded-full transition-all"
                            style={{
                              width: `${Math.min(100, ((gateStatus.verification_day ?? 1) / 30) * 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    )}
                    {gateStatus.win_rate != null && (
                      <div className="space-y-1">
                        <div className="flex justify-between text-[10px] text-gray-500 uppercase tracking-wide">
                          <span>Win rate {formatPct(gateStatus.win_rate)}</span>
                          <span>Target 55%</span>
                        </div>
                        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-apex-green/80 rounded-full transition-all"
                            style={{
                              width: `${Math.min(100, (gateStatus.win_rate / 0.55) * 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    )}
                    <p className="text-xs text-gray-500">{gateStatus.recommendation}</p>
                    {liveGateTightening?.active && (
                      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs">
                        <p className="text-amber-400 font-medium mb-1">
                          Gate entry tightening active (WR{" "}
                          {formatPct(liveGateTightening.win_rate)} &lt; 55%)
                          {connected && gateEntryTightening && (
                            <span className="text-amber-500/70"> · live WS</span>
                          )}
                        </p>
                        <div className="space-y-0.5 text-gray-400">
                          <p>
                            Min sentiment: {liveGateTightening.min_sentiment.toFixed(2)}
                            {liveGateTightening.require_macd_bullish &&
                              " · MACD bullish required"}
                          </p>
                          <p>
                            PM max positions: {liveGateTightening.max_pm_open_positions}
                            {liveGateTightening.max_crypto_open_positions != null && (
                              <span>
                                {" "}
                                · crypto max {liveGateTightening.max_crypto_open_positions}
                              </span>
                            )}
                            {liveGateTightening.max_commodities_open_positions != null && (
                              <span>
                                {" "}
                                · commodities max{" "}
                                {liveGateTightening.max_commodities_open_positions}
                              </span>
                            )}
                            {liveGateTightening.max_stocks_open_positions != null && (
                              <span>
                                {" "}
                                · stocks max{" "}
                                {liveGateTightening.max_stocks_open_positions}
                              </span>
                            )}
                            {liveGateTightening.min_composite_boost > 0 && (
                              <span>
                                {" "}
                                · composite boost +{liveGateTightening.min_composite_boost.toFixed(2)}
                              </span>
                            )}
                          </p>
                          {(liveGateTightening.blocked_new_entries?.length ?? 0) > 0 && (
                            <p className="text-amber-300/90">
                              No new entries:{" "}
                              {liveGateTightening.blocked_new_entries
                                ?.map((b) => botLabel(b))
                                .join(", ")}
                              {" "}(WR &lt; 40%, ≥15 trades)
                            </p>
                          )}
                          {liveGateTightening.stocks_proven_winners_only && (
                            <p className="text-emerald-300 font-medium">
                              Stocks: proven winners only (NVDA-only new entries during gate)
                            </p>
                          )}
                          {liveGateTightening.proven_winner_symbols &&
                            Object.keys(liveGateTightening.proven_winner_symbols).length > 0 && (
                              <p className="text-emerald-400/90">
                                Proven winners (easier entries):{" "}
                                {Object.entries(liveGateTightening.proven_winner_symbols)
                                  .map(([bot, syms]) => `${botLabel(bot)}: ${syms.join(", ")}`)
                                  .join(" · ")}
                              </p>
                            )}
                          {liveGateTightening.recent_loser_symbols &&
                            Object.keys(liveGateTightening.recent_loser_symbols).length > 0 && (
                              <p className="text-orange-400/80">
                                Recent losers (7d, skipped):{" "}
                                {Object.entries(liveGateTightening.recent_loser_symbols)
                                  .map(([bot, syms]) =>
                                    `${botLabel(bot)}: ${syms.slice(0, 3).join(", ")}${syms.length > 3 ? "…" : ""}`
                                  )
                                  .join(" · ")}
                              </p>
                            )}
                          {liveGateTightening.chronic_loser_symbols &&
                            Object.keys(liveGateTightening.chronic_loser_symbols).length > 0 && (
                              <p className="text-red-400/80">
                                Chronic losers (skipped):{" "}
                                {Object.entries(liveGateTightening.chronic_loser_symbols)
                                  .map(([bot, syms]) =>
                                    `${botLabel(bot)}: ${syms.slice(0, 3).join(", ")}${syms.length > 3 ? "…" : ""}`
                                  )
                                  .join(" · ")}
                              </p>
                            )}
                        </div>
                      </div>
                    )}
                    {gateStatus.paused_bots && gateStatus.paused_bots.length > 0 && (
                      <p className="text-xs text-amber-500/90">
                        Gate excludes paused bots: {gateStatus.paused_bots.join(", ")}
                        {gateStatus.aggregate && (
                          <span className="text-gray-500">
                            {" "}
                            · all-bots PnL {gateStatus.aggregate.total_pnl.toFixed(2)}
                          </span>
                        )}
                      </p>
                    )}
                    {gateStatus.per_bot && Object.keys(gateStatus.per_bot).length > 0 && (
                      <div className="space-y-1 pt-1 border-t border-apex-border/50">
                        <p className="text-[10px] text-gray-500 uppercase tracking-wide">
                          Per-bot graduation (since verification start)
                        </p>
                        {Object.entries(gateStatus.per_bot).map(([bot, stats]) => (
                          <div
                            key={bot}
                            className="flex justify-between items-center text-xs gap-2"
                          >
                            <span className={stats.paused ? "text-amber-400" : "text-gray-300"}>
                              {botLabel(bot)}
                              {stats.paused ? " (paused)" : ""}
                            </span>
                            <span className="text-gray-500 shrink-0">
                              {stats.total_trades} trades · {formatPct(stats.win_rate)} WR · $
                              {stats.total_pnl.toFixed(0)}
                              {stats.graduation_progress && (
                                <span className="text-gray-600">
                                  {" "}
                                  · {Math.round(stats.graduation_progress.overall_pct * 100)}% grad
                                </span>
                              )}
                            </span>
                            <span
                              className={cn(
                                "text-[10px] px-1.5 py-0.5 rounded shrink-0",
                                stats.graduation_ready
                                  ? "bg-apex-green/10 text-apex-green"
                                  : stats.paused
                                    ? "bg-gray-800 text-gray-500"
                                    : "bg-apex-green/5 text-gray-400"
                              )}
                            >
                              {stats.graduation_ready
                                ? "ready"
                                : stats.paused
                                  ? "blocked"
                                  : "active"}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="space-y-1">
                      {Object.entries(gateStatus.checks).map(([key, check]) => (
                        <div key={key} className="flex justify-between text-xs">
                          <span className="text-gray-500">{key.replace(/_/g, " ")}</span>
                          <span className={check.passed ? "text-apex-green" : "text-apex-red"}>
                            {String(check.actual)} / {String(check.required)}
                          </span>
                        </div>
                      ))}
                    </div>
                    {((verificationHistory ?? []).length > 0 || chartEquityHistory.length > 0) && (
                      <div className="pt-2 border-t border-apex-border">
                        <VerificationPnLChart
                          snapshots={verificationHistory ?? []}
                          equityHistory={chartEquityHistory}
                        />
                        <p className="text-xs text-gray-500 mb-2 mt-3">Daily verification log</p>
                        <div className="space-y-1 max-h-32 overflow-y-auto">
                          {(verificationHistory ?? []).slice(0, 7).map((snap) => (
                            <div
                              key={snap.snapshot_date}
                              className="flex justify-between text-xs text-gray-400"
                            >
                              <span>
                                Day {snap.verification_day} · {snap.total_trades} trades
                              </span>
                              <span className={snap.performance_checks_passed ? "text-apex-green" : "text-apex-red"}>
                                {formatPct(snap.win_rate)} · PF {snap.profit_factor.toFixed(2)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">Loading profitability status...</p>
                )}
              </Card>
              <Card title="Portfolios">
                {(portfolios ?? []).map((p) => (
                  <div
                    key={p.bot_type}
                    className="flex justify-between items-center py-3 border-b border-apex-border last:border-0"
                  >
                    <div>
                      <p className="text-sm font-medium text-white">{botLabel(p.bot_type)}</p>
                      <p className="text-xs text-gray-500">
                        {p.total_trades} trades · {formatPct(p.win_rate)} win rate
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium text-white">{formatCurrency(p.equity)}</p>
                      <p className={cn("text-xs", pnlColor(p.total_pnl))}>
                        {formatCurrency(p.total_pnl)}
                      </p>
                    </div>
                  </div>
                ))}
                {(portfolios ?? []).length === 0 && (
                  <p className="text-sm text-gray-500 py-4">Bots initializing portfolios...</p>
                )}
              </Card>
              <Card title="Latest Intelligence">
                {(intelFeed ?? []).slice(0, 5).map((item) => (
                  <div key={item.id} className="py-2 border-b border-apex-border last:border-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-apex-border text-gray-400 uppercase">
                        {item.source}
                      </span>
                      <span className={cn("text-[10px]", sentimentColor(item.sentiment))}>
                        {item.sentiment > 0 ? "+" : ""}
                        {item.sentiment.toFixed(2)}
                      </span>
                    </div>
                    <p className="text-xs text-gray-300 line-clamp-2">{item.title}</p>
                  </div>
                ))}
              </Card>
            </div>
          </div>
        )}

        {tab === "trades" && (
          <Card title="All Trades">
            <TradesTable trades={trades ?? []} />
          </Card>
        )}

        {tab === "positions" && (
          <Card title="Open Positions">
            {(positions ?? []).length === 0 ? (
              <p className="text-sm text-gray-500 py-8 text-center">
                No open positions. Bots are scanning for opportunities...
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-500 text-xs border-b border-apex-border">
                      <th className="text-left py-3 px-2">Bot</th>
                      <th className="text-left py-3 px-2">Symbol</th>
                      <th className="text-right py-3 px-2">Qty</th>
                      <th className="text-right py-3 px-2">Entry</th>
                      <th className="text-right py-3 px-2">Current</th>
                      <th className="text-right py-3 px-2">Unrealized P&L</th>
                      <th className="text-right py-3 px-2">Opened</th>
                      <th className="text-right py-3 px-2">Stop Loss</th>
                      <th className="text-right py-3 px-2">Take Profit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(positions ?? []).map((p) => (
                      <tr key={p.id} className="border-b border-apex-border/50">
                        <td className="py-3 px-2 text-gray-400">{botLabel(p.bot_type)}</td>
                        <td className="py-3 px-2 font-medium text-white">{p.symbol}</td>
                        <td className="py-3 px-2 text-right text-gray-300">
                          {p.quantity.toFixed(4)}
                        </td>
                        <td className="py-3 px-2 text-right text-gray-300">
                          ${p.entry_price.toFixed(2)}
                        </td>
                        <td className="py-3 px-2 text-right text-white">
                          ${p.current_price.toFixed(2)}
                        </td>
                        <td className={cn("py-3 px-2 text-right font-medium", pnlColor(p.unrealized_pnl))}>
                          {formatCurrency(p.unrealized_pnl)}
                        </td>
                        <td className="py-3 px-2 text-right text-gray-500 text-xs">
                          {p.opened_at ? formatTime(p.opened_at) : "—"}
                        </td>
                        <td className="py-3 px-2 text-right text-apex-red">
                          ${p.stop_loss?.toFixed(2)}
                        </td>
                        <td className="py-3 px-2 text-right text-apex-green">
                          ${p.take_profit?.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}

        {tab === "intelligence" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card title="Market Intelligence Feed">
              <div className="space-y-3 max-h-[700px] overflow-y-auto">
                {(intelFeed ?? []).map((item) => (
                  <div
                    key={item.id}
                    className="p-3 rounded-lg bg-apex-dark border border-apex-border"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-apex-purple/20 text-apex-purple uppercase font-medium">
                        {item.source}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-apex-border text-gray-400">
                        {item.category}
                      </span>
                      <span className={cn("text-xs ml-auto", sentimentColor(item.sentiment))}>
                        Sentiment: {item.sentiment > 0 ? "+" : ""}
                        {item.sentiment.toFixed(2)}
                      </span>
                    </div>
                    <p className="text-sm text-white font-medium mb-1">{item.title}</p>
                    <p className="text-xs text-gray-500 line-clamp-2">{item.content}</p>
                    {item.symbols_mentioned && (
                      <p className="text-[10px] text-apex-gold mt-2">
                        Symbols: {item.symbols_mentioned}
                      </p>
                    )}
                    <p className="text-[10px] text-gray-600 mt-1">
                      {formatTime(item.fetched_at)}
                    </p>
                  </div>
                ))}
              </div>
            </Card>
            <Card title="Intelligence Sources">
              <div className="space-y-4">
                {(intelSources ?? [
                  { source: "news", status: "active", items_collected: 0, last_fetched: null },
                  { source: "reddit", status: "active", items_collected: 0, last_fetched: null },
                  { source: "youtube", status: "active", items_collected: 0, last_fetched: null },
                  { source: "x", status: "pending", items_collected: 0, last_fetched: null },
                  { source: "tiktok", status: "active", items_collected: 0, last_fetched: null },
                  { source: "dexscreener", status: "active", items_collected: 0, last_fetched: null },
                  { source: "hyperliquid", status: "active", items_collected: 0, last_fetched: null },
                  { source: "fomo", status: "degraded", items_collected: 0, last_fetched: null },
                  { source: "polymarket", status: "active", items_collected: 0, last_fetched: null },
                  { source: "polymarket_account", status: "active", items_collected: 0, last_fetched: null },
                  { source: "wallet_tracker", status: "active", items_collected: 0, last_fetched: null },
                  { source: "political", status: "active", items_collected: 0, last_fetched: null },
                  { source: "tradingview", status: "pending", items_collected: 0, last_fetched: null },
                  { source: "newsapi", status: "optional", items_collected: 0, last_fetched: null },
                ]).map((src) => (
                  <div
                    key={src.source}
                    className="flex items-center justify-between p-3 rounded-lg bg-apex-dark border border-apex-border"
                  >
                    <div>
                      <p className="text-sm font-medium text-white uppercase">{src.source}</p>
                      <p className="text-xs text-gray-500">
                        {src.items_collected} items collected
                        {src.last_fetched ? ` · last ${formatTime(src.last_fetched)}` : ""}
                        {src.source === "fomo" && src.bearer_polling_active === false && (
                          <span className="text-apex-gold">
                            {" "}
                            · bearer expired
                            {src.bearer_minutes_remaining != null
                              ? ` (${src.bearer_minutes_remaining} min)`
                              : ""}
                          </span>
                        )}
                        {src.source === "fomo" && src.bearer_polling_active && (
                          <span className="text-apex-green">
                            {" "}
                            · poll active
                            {src.bearer_minutes_remaining != null
                              ? ` (${src.bearer_minutes_remaining} min left)`
                              : ""}
                          </span>
                        )}
                        {src.source === "reddit" && src.oauth_configured === false && (
                          <span className="text-apex-gold"> · RSS fallback (OAuth not set)</span>
                        )}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "text-[10px] px-2 py-1 rounded-full font-medium uppercase",
                        src.status === "active"
                          ? "bg-apex-green/10 text-apex-green"
                          : src.status === "degraded"
                            ? "bg-apex-gold/10 text-apex-gold"
                          : src.status === "optional"
                            ? "bg-apex-gold/10 text-apex-gold"
                            : "bg-gray-800 text-gray-500"
                      )}
                    >
                      {src.status}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
            <Card title="Intel Source Routing">
              <IntelRoutingPanel routing={intelRouting} />
            </Card>
          </div>
        )}

        {tab === "learning" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {(platformStatus?.learning?.insights_pending ?? 0) > 0 && (
              <div className="lg:col-span-2 p-3 rounded-lg bg-apex-gold/10 border border-apex-gold/30 text-xs text-apex-gold">
                {platformStatus!.learning!.insights_pending} content-study insight(s) pending
                application — auto-applies every 1h when confidence ≥ 55%.
              </div>
            )}
            <Card title="Loss Trade Analysis">
              <div className="space-y-3 max-h-[500px] overflow-y-auto">
                {(analyses ?? []).length === 0 ? (
                  <p className="text-sm text-gray-500 py-4">No losing trades analyzed yet.</p>
                ) : (
                  (analyses ?? []).map((a) => (
                    <div
                      key={a.id}
                      className="p-3 rounded-lg bg-apex-dark border border-apex-red/20"
                    >
                      <div className="flex justify-between mb-2">
                        <span className="text-sm font-medium text-white">
                          {a.symbol} ({botLabel(a.bot_type)})
                        </span>
                        <span className="text-sm text-apex-red">
                          -{formatCurrency(a.loss_amount)}
                        </span>
                      </div>
                      <p className="text-xs text-apex-red mb-1">
                        <strong>Root cause:</strong> {a.root_cause}
                      </p>
                      {a.market_context && (
                        <p className="text-xs text-gray-500 mb-1">
                          <strong>Context:</strong> {a.market_context.slice(0, 200)}
                          {a.market_context.length > 200 ? "…" : ""}
                        </p>
                      )}
                      <p className="text-xs text-gray-400 mb-1">
                        <strong>Lesson:</strong> {a.lessons_learned}
                      </p>
                      <p className="text-xs text-apex-gold">
                        <strong>Adjustment:</strong> {a.strategy_adjustment}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </Card>
            <Card title="Daily Reviews">
              <div className="space-y-3 max-h-[500px] overflow-y-auto">
                {(reviews ?? []).length === 0 ? (
                  <p className="text-sm text-gray-500 py-4">
                    Daily reviews run at 22:00 UTC. First review coming soon.
                  </p>
                ) : (
                  (reviews ?? []).map((r) => (
                    <div
                      key={r.id}
                      className="p-3 rounded-lg bg-apex-dark border border-apex-border"
                    >
                      <div className="flex justify-between mb-2">
                        <span className="text-sm font-medium text-white">
                          {botLabel(r.bot_type)} — {r.review_date}
                        </span>
                        <span className={cn("text-sm font-medium", pnlColor(r.net_pnl))}>
                          {formatCurrency(r.net_pnl)}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400">
                        {r.total_trades} trades · {formatPct(r.win_rate)} win rate ·{" "}
                        {r.losing_trades} losses
                      </p>
                      <p className="text-xs text-gray-300 mt-2">{r.conclusions}</p>
                      {r.patterns_found && (
                        <p className="text-xs text-apex-purple mt-1">
                          <strong>Patterns:</strong> {r.patterns_found}
                        </p>
                      )}
                      <p className="text-xs text-apex-gold mt-1">{r.strategy_changes}</p>
                    </div>
                  ))
                )}
              </div>
            </Card>
            <Card title="External Content Study">
              <div className="space-y-3 max-h-[320px] overflow-y-auto">
                {(contentStudy?.recent ?? []).length === 0 ? (
                  <p className="text-sm text-gray-500 py-4">
                    No content-study highlights yet — runs hourly from YouTube, Reddit, and live intel.
                  </p>
                ) : (
                  (contentStudy?.recent ?? []).map((row, idx) => (
                    <div
                      key={`${row.source_type}-${idx}`}
                      className="p-3 rounded-lg bg-apex-dark border border-apex-border"
                    >
                      <div className="flex justify-between gap-2 mb-1">
                        <span className="text-xs uppercase text-gray-500">{row.source_type}</span>
                        <span
                          className={cn(
                            "text-[10px] px-2 py-0.5 rounded-full",
                            row.applied
                              ? "bg-apex-green/10 text-apex-green"
                              : "bg-apex-gold/10 text-apex-gold"
                          )}
                        >
                          {row.applied ? "applied" : "pending"}
                        </span>
                      </div>
                      <p className="text-sm text-white font-medium">{row.title}</p>
                      <p className="text-xs text-gray-400 mt-1">{row.impact}</p>
                      <p className="text-[10px] text-gray-600 mt-1">
                        confidence {Math.round(row.confidence * 100)}%
                      </p>
                    </div>
                  ))
                )}
              </div>
              {contentStudy && (
                <p className="text-[10px] text-gray-500 mt-3">
                  {contentStudy.insights_applied} insights applied to strategy parameters
                </p>
              )}
            </Card>
            <Card title="External Knowledge Applied">
              <div className="space-y-3 max-h-[500px] overflow-y-auto lg:col-span-2">
                {(insights ?? []).map((i) => (
                  <div
                    key={i.id}
                    className="p-3 rounded-lg bg-apex-dark border border-apex-border"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-apex-blue/20 text-apex-blue uppercase">
                        {i.source_type}
                      </span>
                      {i.applied && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-apex-green/10 text-apex-green">
                          APPLIED
                        </span>
                      )}
                      <span className="text-[10px] text-gray-500 ml-auto">
                        Confidence: {(i.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p className="text-sm text-white font-medium">{i.source_title}</p>
                    <p className="text-xs text-gray-400 mt-1">{i.key_takeaways}</p>
                    <p className="text-xs text-apex-gold mt-1">Impact: {i.strategy_impact}</p>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}

        {tab === "strategy" && (
          <Card title="Strategy Configuration (Auto-Adapting)">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {(strategies ?? []).map((s) => (
                <div
                  key={s.bot_type}
                  className="p-4 rounded-lg bg-apex-dark border border-apex-border"
                >
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-bold text-white">{botLabel(s.bot_type)}</h3>
                    <span className="text-[10px] px-2 py-1 rounded-full bg-apex-purple/20 text-apex-purple">
                      v{s.version}
                    </span>
                  </div>
                  <div className="space-y-2 text-xs">
                    {[
                      ["RSI Oversold", s.rsi_oversold],
                      ["RSI Overbought", s.rsi_overbought],
                      ["Min Signal Score", s.min_signal_score],
                      ["Min Sentiment", s.min_sentiment_score],
                      ["Stop Loss", `${(s.stop_loss_pct * 100).toFixed(1)}%`],
                      ["Take Profit", `${(s.take_profit_pct * 100).toFixed(1)}%`],
                      ["Max Position", `${(s.max_position_pct * 100).toFixed(1)}%`],
                    ].map(([label, value]) => (
                      <div key={String(label)} className="flex justify-between">
                        <span className="text-gray-500">{label}</span>
                        <span className="text-white font-medium">{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {(strategies ?? []).length === 0 && (
                <p className="text-sm text-gray-500 col-span-3 py-4 text-center">
                  Strategy configs will appear after bots initialize.
                </p>
              )}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
  valueClass,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="p-4 rounded-xl bg-apex-card border border-apex-border">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-500">{label}</span>
        {icon}
      </div>
      <p className={cn("text-xl font-bold", valueClass || "text-white")}>{value}</p>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-apex-card border border-apex-border p-5">
      <h2 className="text-sm font-bold text-white mb-4">{title}</h2>
      {children}
    </div>
  );
}

function BotCard({
  bot,
  session,
  sessionPrep,
  gate,
}: {
  bot: {
    bot_type: string;
    status: string;
    last_action: string;
    last_scan_at?: string | null;
    trades_today: number;
    pnl_today: number;
    strategy_version: number;
  };
  sessionPrep?: SessionPrepEntry;
  session?: {
    in_session: boolean;
    mode:
      | "entries"
      | "winddown"
      | "winddown_only"
      | "pre_session"
      | "outside_session"
      | "weekend_closed";
    minutes_until_open?: number;
    minutes_until_close?: number | null;
  };
  gate?: {
    blocked?: boolean;
    provenWinners?: string[];
    graduation?: {
      paused: boolean;
      graduation_ready: boolean;
      total_trades: number;
      win_rate: number;
      graduation_blockers: string[];
    };
  };
}) {
  const sessionHint =
    session && bot.bot_type === "stocks_futures" && !session.in_session && session.minutes_until_open
      ? `Opens in ${Math.floor(session.minutes_until_open / 60)}h ${session.minutes_until_open % 60}m`
      : session && bot.bot_type === "stocks_futures" && session.in_session && session.minutes_until_close
        ? `Closes in ${Math.floor(session.minutes_until_close / 60)}h ${session.minutes_until_close % 60}m`
        : session && bot.bot_type === "commodities" && !session.in_session && session.minutes_until_open
          ? `CME reopens in ${Math.floor(session.minutes_until_open / 60)}h ${session.minutes_until_open % 60}m`
          : null;
  const preSessionPrep = sessionPrep?.prep_active
    ? sessionPrep.extended_weekend_prep
      ? `Weekend TV prep · ${sessionPrep.nudge_label ?? "nudge"}`
      : "TV prep active"
    : session &&
        bot.bot_type === "stocks_futures" &&
        !session.in_session &&
        session.minutes_until_open != null &&
        session.minutes_until_open <= 90
      ? "TV prep active"
      : session &&
          bot.bot_type === "commodities" &&
          !session.in_session &&
          session.minutes_until_open != null &&
          session.minutes_until_open <= 90
        ? "Futures reopen prep"
        : null;
  return (
    <div className="p-4 rounded-lg bg-apex-dark border border-apex-border">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Bot size={16} className="text-apex-gold" />
        <span className="text-sm font-bold text-white">{botLabel(bot.bot_type)}</span>
        {gate?.blocked && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-red-500/10 text-red-400">
            entries blocked
          </span>
        )}
        {gate?.graduation?.paused && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-amber-500/10 text-amber-400">
            shadow mode
          </span>
        )}
        {gate?.graduation?.graduation_ready && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-apex-green/10 text-apex-green">
            ready to unpause
          </span>
        )}
        {gate?.provenWinners && gate.provenWinners.length > 0 && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-emerald-500/10 text-emerald-400">
            {gate.provenWinners.join(", ")}
          </span>
        )}
        {session && bot.bot_type === "commodities" && (
          <span
            className={cn(
              "text-[10px] px-2 py-0.5 rounded-full font-medium",
              session.in_session
                ? "bg-apex-green/10 text-apex-green"
                : "bg-apex-purple/10 text-apex-purple"
            )}
          >
            {session.in_session ? "CME open" : "Weekend · stale feeds"}
          </span>
        )}
        {session && bot.bot_type === "stocks_futures" && (
          <span
            className={cn(
              "text-[10px] px-2 py-0.5 rounded-full font-medium",
              session.in_session
                ? "bg-apex-green/10 text-apex-green"
                : "bg-apex-purple/10 text-apex-purple"
            )}
          >
            {session.in_session ? "US session" : "After hours · wind-down"}
          </span>
        )}
        {preSessionPrep && (
          <span className="text-[10px] text-apex-gold/90">{preSessionPrep}</span>
        )}
        {sessionHint && (
          <span className="text-[10px] text-gray-500">{sessionHint}</span>
        )}
        <span
          className={cn(
            "ml-auto text-[10px] px-2 py-0.5 rounded-full font-medium uppercase",
            bot.status === "running"
              ? "bg-apex-green/10 text-apex-green"
              : "bg-apex-gold/10 text-apex-gold"
          )}
        >
          {bot.status}
        </span>
      </div>
      <p className="text-xs text-gray-400 mb-2 line-clamp-2">{bot.last_action}</p>
      {gate?.graduation?.paused && (
        <p className="text-[10px] text-gray-500 mb-2">
          Gate: {gate.graduation.total_trades} trades · {formatPct(gate.graduation.win_rate)} WR
          {gate.graduation.graduation_blockers.length > 0 && (
            <span className="text-gray-600">
              {" "}
              · needs {gate.graduation.graduation_blockers.join(", ")}
            </span>
          )}
        </p>
      )}
      {(gate?.graduation?.paused ||
        (bot.bot_type === "commodities" && session && !session.in_session) ||
        (bot.bot_type === "stocks_futures" && session && !session.in_session)) && (
        <BotScanPreview botType={bot.bot_type} />
      )}
      <div className="flex justify-between text-[10px] text-gray-500">
        <span>{bot.trades_today} trades today</span>
        <span>Strategy v{bot.strategy_version}</span>
      </div>
    </div>
  );
}

function SessionPrepBanner({ sessionPrep }: { sessionPrep: SessionPrepStatus | null }) {
  if (!sessionPrep) return null;

  const rows = (["stocks_futures", "commodities"] as const)
    .map((key) => sessionPrep[key])
    .filter((entry) => entry?.prep_active);

  if (rows.length === 0) return null;

  return (
    <div className="rounded-lg border border-apex-gold/30 bg-apex-gold/5 p-4">
      <p className="text-sm font-medium text-apex-gold mb-2">Session prep active</p>
      <ul className="space-y-1.5">
        {rows.map((entry) => {
          const mins = entry.minutes_until_open;
          const openLabel =
            mins != null ? `${Math.floor(mins / 60)}h ${mins % 60}m until open` : "open soon";
          return (
            <li key={entry.bot_type} className="text-xs text-gray-300">
              <span className="font-medium text-white">{botLabel(entry.bot_type)}</span>
              {" · "}
              {entry.extended_weekend_prep ? "weekend TV prep" : "TV prep"}
              {entry.nudge_label ? ` · ${entry.nudge_label}` : ""}
              {" · "}
              <span className="text-gray-500">{openLabel}</span>
              {entry.session_mode ? (
                <span className="text-gray-600"> · {entry.session_mode}</span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function MondayRecoveryBanner({ summary }: { summary: MondayRecoverySummary | null }) {
  const hasNudge = summary?.stocks_trade_count_nudge || summary?.commodities_graduation_nudge;
  if (!summary?.all?.length && !hasNudge) return null;

  return (
    <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
      <p className="text-sm font-medium text-emerald-400 mb-2">Monday recovery watchlist</p>
      {summary.stocks_trade_count_nudge && (
        <p className="text-[11px] text-amber-400/90 mb-2">
          Stocks trade-count nudge active — proven winners scanned first (composite floor 0.34).
        </p>
      )}
      {summary.commodities_graduation_nudge && (
        <p className="text-[11px] text-amber-400/90 mb-2">
          Commodities graduation nudge active — recovery futures prioritized for CME reopen.
        </p>
      )}
      {summary.all?.length ? (
        <ul className="space-y-1.5">
          {summary.all.map((row) => (
            <li
              key={`${row.bot_type}-${row.symbol}`}
              className="flex items-center justify-between gap-3 text-xs"
            >
              <span className="text-gray-200 font-medium">
                {botLabel(row.bot_type)} · {row.symbol}
              </span>
              <span className="text-gray-500 text-right">
                composite {(row.composite ?? 0).toFixed(3)}
                {(row.blockers?.length ?? 0) > 0 && (
                  <span className="text-gray-600"> · {row.blockers!.slice(0, 2).join(", ")}</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[11px] text-gray-500">
          No recovery-ready symbols right now — nudges still active.
        </p>
      )}
    </div>
  );
}

function BotScanPreview({ botType }: { botType: string }) {
  const [preview, setPreview] = useState<ScanPreview | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchAPI<ScanPreview>(`/bots/${botType}/scan-preview`)
      .then((data) => {
        if (!cancelled) setPreview(data);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [botType]);

  if (error) return null;
  if (!preview) {
    return <p className="text-[10px] text-gray-600 mb-2">Scan preview loading…</p>;
  }

  const rows = preview.symbols.filter((row) => !row.skip);
  const recoveryRows = rows.filter((row) => row.recovery_ready);
  const fillerCount = recoveryRows.length > 0 ? 1 : 2;
  const topRows = rows
    .filter((row) => !row.recovery_ready)
    .sort((a, b) => (b.composite ?? 0) - (a.composite ?? 0))
    .slice(0, fillerCount);
  const candidates = [...recoveryRows, ...topRows].slice(0, 3);

  if (candidates.length === 0) return null;

  return (
    <div className="mb-2 rounded border border-apex-border/60 bg-apex-dark/40 p-2">
      <p className="text-[10px] text-gray-500 mb-1">
        Scan preview
        {preview.open_count != null && preview.shadow_open_cap != null && (
          <span className="text-gray-400">
            {" "}
            · {preview.open_count}/{preview.shadow_open_cap} open
          </span>
        )}
        {preview.graduation_nudge && (
          <span className="text-amber-500/90"> · graduation nudge</span>
        )}
        {preview.stocks_trade_count_nudge && (
          <span className="text-amber-400/90"> · trade-count nudge (floor 0.34 / sent 0.05)</span>
        )}
        {preview.crypto_strong_momentum_nudge && (
          <span className="text-emerald-400/90"> · strong momentum (cap 4 / loss cut $2.50)</span>
        )}
        {preview.crypto_pre_graduation_nudge && (
          <span className="text-sky-400/90"> · pre-graduation (loss cut $2.00)</span>
        )}
        {preview.crypto_cap_pressure_active && (
          <span className="text-rose-400/90" title="At shadow cap — fast loser exits active (60s@-$6, 180s@-$4, 300s@-$2)">
            {" "}
            · cap pressure
          </span>
        )}
        {preview.crypto_shadow_raw_floor_active
          && !preview.crypto_momentum_retreat
          && preview.crypto_momentum_retreat_min_raw_signal != null && (
          <span className="text-amber-300/90" title="Raw technical floor until 50% WR">
            {" "}
            · raw floor {preview.crypto_momentum_retreat_min_raw_signal}
          </span>
        )}
        {preview.crypto_momentum_retreat && (
          <span className="text-amber-400/90" title="WR/PF below momentum tier — entry filters tightened">
            {" "}
            · momentum retreat
            {preview.crypto_momentum_retreat_min_signal != null && (
              <span> (floor {preview.crypto_momentum_retreat_min_signal}</span>
            )}
            {preview.crypto_momentum_retreat_max_open != null && (
              <span>
                {preview.crypto_momentum_retreat_min_signal != null ? ", " : " ("}
                cap {preview.crypto_momentum_retreat_max_open}
              </span>
            )}
            {preview.crypto_momentum_retreat_min_raw_signal != null && (
              <span>
                {(preview.crypto_momentum_retreat_min_signal != null
                  || preview.crypto_momentum_retreat_max_open != null)
                  ? ", "
                  : " ("}
                raw {preview.crypto_momentum_retreat_min_raw_signal}
              </span>
            )}
            {(preview.crypto_momentum_retreat_min_signal != null
              || preview.crypto_momentum_retreat_max_open != null
              || preview.crypto_momentum_retreat_min_raw_signal != null) && (
              <span>)</span>
            )}
            {" "}
            · profit lock $1.25
            {preview.crypto_momentum_retreat_loss_wind_down_usd != null && (
              <span>
                {" "}
                · loss wind-down ${preview.crypto_momentum_retreat_loss_wind_down_usd}
              </span>
            )}
          </span>
        )}
        {preview.open_ready_candidates && preview.open_ready_candidates.length > 0 && (
          <span className="text-lime-400/90">
            {" "}
            · CME open ready: {preview.open_ready_candidates.join(", ")}
          </span>
        )}
        {preview.commodities_gate_loss_wind_down_usd != null && (
          <span className="text-amber-300/90" title="Active gate commodities graduation loss wind-down">
            {" "}
            · gate loss wind-down ${preview.commodities_gate_loss_wind_down_usd}
          </span>
        )}
        {preview.recovery_candidates && preview.recovery_candidates.length > 0 && (
          <span className="text-emerald-400/90">
            {" "}
            · recovery: {preview.recovery_candidates.join(", ")}
          </span>
        )}
      </p>
      <ul className="space-y-1">
        {candidates.map((row) => (
          <li key={row.symbol} className="flex items-center justify-between gap-2 text-[10px]">
            <span className="text-gray-300 font-medium">
              {row.symbol}
              {row.recovery_ready && (
                <span className="ml-1 text-emerald-400/80">↗</span>
              )}
              {row.monday_gate_skip_ready && (
                <span className="ml-1 text-sky-400/80" title="Monday gate-skip bypass eligible">
                  M
                </span>
              )}
            </span>
            <span
              className={
                row.recovery_ready
                  ? "text-emerald-400"
                  : row.would_enter
                    ? "text-apex-green"
                    : "text-gray-500"
              }
            >
              {row.recovery_ready
                ? "recovery ready"
                : row.would_enter
                  ? "would enter"
                  : (row.blockers ?? []).slice(0, 2).join(", ")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TradesTable({ trades, compact }: { trades: Trade[]; compact?: boolean }) {
  if (trades.length === 0) {
    return (
      <p className="text-sm text-gray-500 py-8 text-center">
        No trades yet. Bots are actively scanning markets...
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-500 text-xs border-b border-apex-border">
            <th className="text-left py-2 px-2">Time</th>
            <th className="text-left py-2 px-2">Bot</th>
            <th className="text-left py-2 px-2">Symbol</th>
            <th className="text-left py-2 px-2">Action</th>
            <th className="text-right py-2 px-2">Price</th>
            {!compact && <th className="text-right py-2 px-2">Signal</th>}
            <th className="text-right py-2 px-2">P&L</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} className="border-b border-apex-border/50">
              <td className="py-2 px-2 text-gray-500 text-xs">{formatTime(t.executed_at)}</td>
              <td className="py-2 px-2 text-gray-400 text-xs">{botLabel(t.bot_type)}</td>
              <td className="py-2 px-2 font-medium text-white">{t.symbol}</td>
              <td className="py-2 px-2">
                <span
                  className={cn(
                    "text-xs px-2 py-0.5 rounded font-medium uppercase",
                    t.action === "buy"
                      ? "bg-apex-green/10 text-apex-green"
                      : "bg-apex-red/10 text-apex-red"
                  )}
                >
                  {t.action}
                </span>
              </td>
              <td className="py-2 px-2 text-right text-gray-300">${t.price.toFixed(2)}</td>
              {!compact && (
                <td className="py-2 px-2 text-right text-gray-400">
                  {t.signal_score.toFixed(2)}
                </td>
              )}
              <td className={cn("py-2 px-2 text-right font-medium", pnlColor(t.pnl))}>
                {t.action === "sell" ? formatCurrency(t.pnl) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
