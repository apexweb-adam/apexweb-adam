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
  StrategyConfig,
  ProfitabilityStatus,
  VerificationSnapshot,
  IntelligenceSource,
  PlatformStatus,
  DashboardConfig,
  IntelRouting,
  ActiveGateStatus,
  EquityHistoryPoint,
} from "@/lib/api";
import { enrichProfitabilityStatus, activeGateToProfitability, buildEquityHistoryFromTrades } from "@/lib/profitability";
import { VerificationPnLChart } from "@/components/VerificationPnLChart";
import { IntelRoutingPanel } from "@/components/IntelRoutingPanel";

type Tab = "overview" | "trades" | "positions" | "intelligence" | "learning" | "strategy";

export default function Dashboard() {
  const { stats, portfolios, bots, positions: livePositions, trades: liveTrades, recentIntel, connected, lastUpdate, lastTrade } = useLiveData();
  const { data: tradesRest } = useAPI<Trade[]>("/trades?limit=50", 30000);
  const { data: gateTradesRest } = useAPI<Trade[]>("/trades?limit=200", 30000);
  const { data: positionsRest } = useAPI<Position[]>("/positions", 30000);
  const trades = connected ? liveTrades : (tradesRest ?? []);
  const positions = connected ? livePositions : (positionsRest ?? []);
  const { data: intelligence } = useAPI<IntelligenceItem[]>("/intelligence?limit=30", 15000);
  const { data: analyses } = useAPI<TradeAnalysis[]>("/analyses?limit=20", 15000);
  const { data: reviews } = useAPI<DailyReview[]>("/reviews?limit=10", 30000);
  const { data: insights } = useAPI<LearningInsight[]>("/insights?limit=20", 30000);
  const { data: strategies } = useAPI<StrategyConfig[]>("/strategies", 30000);
  const { data: profitability } = useAPI<ProfitabilityStatus>("/profitability", 15000);
  const { data: activeGate } = useAPI<ActiveGateStatus>("/active-gate", 15000);
  const { data: verificationHistory } = useAPI<VerificationSnapshot[]>(
    "/verification/history?limit=30",
    60000
  );
  const { data: equityHistory } = useAPI<EquityHistoryPoint[]>("/equity-history", 60000);
  const { data: intelSources } = useAPI<IntelligenceSource[]>("/intelligence/sources", 30000);
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
      if (!byId.has(item.id)) {
        byId.set(item.id, {
          ...item,
          content: item.title,
          url: "",
          symbols_mentioned: "",
        });
      }
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
    if ((equityHistory?.length ?? 0) > 0) return equityHistory!;
    if ((profitability?.equity_history?.length ?? 0) > 0) return profitability!.equity_history!;
    return equityHistoryFromTrades;
  }, [equityHistory, profitability, equityHistoryFromTrades]);

  const gateStatus = useMemo(() => {
    if (activeGate?.active_bots) {
      return activeGateToProfitability(activeGate, profitability ?? undefined);
    }
    return enrichProfitabilityStatus(
      profitability ?? undefined,
      gateTrades,
      portfolios,
      strategies
    );
  }, [activeGate, profitability, gateTrades, portfolios, strategies]);

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
              <Card title="Bot Status">
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                  {bots.map((bot) => (
                    <BotCard key={bot.bot_type} bot={bot} />
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
                    <p className="text-xs text-gray-500">{gateStatus.recommendation}</p>
                    {platformStatus?.gate_entry_tightening?.active && (
                      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs">
                        <p className="text-amber-400 font-medium mb-1">
                          Gate entry tightening active (WR{" "}
                          {formatPct(platformStatus.gate_entry_tightening.win_rate)} &lt; 55%)
                        </p>
                        <div className="space-y-0.5 text-gray-400">
                          <p>
                            Min sentiment: {platformStatus.gate_entry_tightening.min_sentiment.toFixed(2)}
                            {platformStatus.gate_entry_tightening.require_macd_bullish &&
                              " · MACD bullish required"}
                          </p>
                          <p>
                            PM max positions: {platformStatus.gate_entry_tightening.max_pm_open_positions}
                            {platformStatus.gate_entry_tightening.max_crypto_open_positions != null && (
                              <span>
                                {" "}
                                · crypto max {platformStatus.gate_entry_tightening.max_crypto_open_positions}
                              </span>
                            )}
                            {platformStatus.gate_entry_tightening.max_commodities_open_positions != null && (
                              <span>
                                {" "}
                                · commodities max{" "}
                                {platformStatus.gate_entry_tightening.max_commodities_open_positions}
                              </span>
                            )}
                            {platformStatus.gate_entry_tightening.min_composite_boost > 0 && (
                              <span>
                                {" "}
                                · composite boost +{platformStatus.gate_entry_tightening.min_composite_boost.toFixed(2)}
                              </span>
                            )}
                          </p>
                          {(platformStatus.gate_entry_tightening.blocked_new_entries?.length ?? 0) > 0 && (
                            <p className="text-amber-300/90">
                              No new entries:{" "}
                              {platformStatus.gate_entry_tightening.blocked_new_entries
                                ?.map((b) => botLabel(b))
                                .join(", ")}
                              {" "}(WR &lt; 40%, ≥15 trades)
                            </p>
                          )}
                          {platformStatus.gate_entry_tightening.proven_winner_symbols &&
                            Object.keys(platformStatus.gate_entry_tightening.proven_winner_symbols).length > 0 && (
                              <p className="text-emerald-400/90">
                                Proven winners (easier entries):{" "}
                                {Object.entries(platformStatus.gate_entry_tightening.proven_winner_symbols)
                                  .map(([bot, syms]) => `${botLabel(bot)}: ${syms.join(", ")}`)
                                  .join(" · ")}
                              </p>
                            )}
                          {platformStatus.gate_entry_tightening.chronic_loser_symbols &&
                            Object.keys(platformStatus.gate_entry_tightening.chronic_loser_symbols).length > 0 && (
                              <p className="text-red-400/80">
                                Chronic losers (skipped):{" "}
                                {Object.entries(platformStatus.gate_entry_tightening.chronic_loser_symbols)
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
                  { source: "polymarket", status: "active", items_collected: 0, last_fetched: null },
                  { source: "political", status: "active", items_collected: 0, last_fetched: null },
                  { source: "tiktok", status: "active", items_collected: 0, last_fetched: null },
                  { source: "x", status: "pending", items_collected: 0, last_fetched: null },
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
                      <p className="text-xs text-apex-gold mt-1">{r.strategy_changes}</p>
                    </div>
                  ))
                )}
              </div>
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

function BotCard({ bot }: { bot: { bot_type: string; status: string; last_action: string; last_scan_at?: string | null; trades_today: number; pnl_today: number; strategy_version: number } }) {
  return (
    <div className="p-4 rounded-lg bg-apex-dark border border-apex-border">
      <div className="flex items-center gap-2 mb-3">
        <Bot size={16} className="text-apex-gold" />
        <span className="text-sm font-bold text-white">{botLabel(bot.bot_type)}</span>
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
      <div className="flex justify-between text-[10px] text-gray-500">
        <span>{bot.trades_today} trades today</span>
        <span>Strategy v{bot.strategy_version}</span>
      </div>
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
