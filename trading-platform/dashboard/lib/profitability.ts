import type { Portfolio, ProfitabilityStatus, StrategyConfig, Trade } from "./api";

const MIN_TRADES = 100;
const MIN_WIN_RATE = 0.55;
const MIN_PROFIT_FACTOR = 1.3;
const MIN_DAYS = 30;

function aggregateWinRate(sells: Trade[]): number {
  const winners = sells.filter((t) => t.is_winner === true).length;
  const losers = sells.filter((t) => t.is_winner === false).length;
  const decided = winners + losers;
  return decided ? winners / decided : 0;
}

function profitFactor(sells: Trade[]): number | null {
  const winners = sells.filter((t) => t.is_winner === true);
  const losers = sells.filter((t) => t.is_winner === false);
  const grossProfit = winners.reduce((sum, t) => sum + t.pnl, 0);
  const grossLoss = Math.abs(losers.reduce((sum, t) => sum + t.pnl, 0));
  if (grossLoss <= 0) return grossProfit > 0 ? null : 0;
  return grossProfit / grossLoss;
}

/** Infer paused bots when backend gate has not been deployed yet. */
export function inferPausedBots(strategies: StrategyConfig[] | undefined): string[] {
  if (!strategies?.length) return [];
  return strategies.filter((s) => s.max_position_pct <= 0).map((s) => s.bot_type);
}

/** Client-side active-bot gate when backend omits paused_bots (stale Render deploy). */
export function enrichProfitabilityStatus(
  api: ProfitabilityStatus | undefined,
  trades: Trade[],
  portfolios: Portfolio[] | undefined,
  strategies: StrategyConfig[] | undefined | null
): ProfitabilityStatus | undefined {
  if (!api) return undefined;

  const pausedFromApi = api.paused_bots ?? [];
  const pausedFromStrategies = inferPausedBots(strategies ?? undefined);
  const pausedBots = pausedFromApi.length ? pausedFromApi : pausedFromStrategies;
  if (!pausedBots.length) return api;

  const pausedSet = new Set(pausedBots);
  const sells = trades.filter((t) => t.action === "sell" && !pausedSet.has(t.bot_type));
  const activePortfolios = (portfolios ?? []).filter((p) => !pausedSet.has(p.bot_type));

  const winRate = aggregateWinRate(sells);
  const pf = profitFactor(sells);
  const totalPnl = activePortfolios.reduce((sum, p) => sum + p.total_pnl, 0);
  const totalTrades = sells.length;
  const daysTrading = api.days_trading ?? 0;
  const verificationDay = api.verification_day ?? daysTrading + 1;

  const checks = {
    ...api.checks,
    min_trades: {
      required: MIN_TRADES,
      actual: totalTrades,
      passed: totalTrades >= MIN_TRADES,
    },
    min_win_rate: {
      required: MIN_WIN_RATE,
      actual: winRate,
      passed: winRate >= MIN_WIN_RATE,
    },
    min_profit_factor: {
      required: MIN_PROFIT_FACTOR,
      actual: pf != null ? Math.round(pf * 100) / 100 : pf,
      passed: pf != null && pf >= MIN_PROFIT_FACTOR,
    },
    positive_pnl: {
      required: 0,
      actual: totalPnl,
      passed: totalPnl > 0,
    },
    min_days: api.checks.min_days,
    paper_trading_only: api.checks.paper_trading_only,
  };

  const blockers: string[] = [];
  if (totalTrades < MIN_TRADES) blockers.push(`${MIN_TRADES - totalTrades} more trades`);
  if (daysTrading < MIN_DAYS) blockers.push(`${Math.max(0, MIN_DAYS - verificationDay)} more days`);
  if (totalPnl <= 0) blockers.push("positive PnL");
  if (pf == null || pf < MIN_PROFIT_FACTOR) blockers.push(`profit factor ≥ ${MIN_PROFIT_FACTOR}`);
  if (winRate < MIN_WIN_RATE) blockers.push(`win rate ≥ ${Math.round(MIN_WIN_RATE * 100)}%`);

  const liveReady =
    totalTrades >= MIN_TRADES &&
    winRate >= MIN_WIN_RATE &&
    pf != null &&
    pf >= MIN_PROFIT_FACTOR &&
    totalPnl > 0 &&
    daysTrading >= MIN_DAYS;

  return {
    ...api,
    paused_bots: pausedBots,
    total_trades: totalTrades,
    win_rate: winRate,
    profit_factor: pf != null ? Math.round(pf * 100) / 100 : pf,
    total_pnl: totalPnl,
    live_trading_ready: liveReady,
    checks,
    recommendation:
      (liveReady ? "READY for live trading review" : `Continue paper trading — need ${blockers.join(", ")}`) +
      ` (excludes paused: ${pausedBots.join(", ")})`,
    aggregate: api.aggregate ?? {
      total_trades: api.total_trades,
      win_rate: api.win_rate,
      profit_factor: api.profit_factor,
      total_pnl: api.total_pnl,
    },
  };
}
