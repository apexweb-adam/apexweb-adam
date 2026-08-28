import type { EquityHistoryPoint, PerBotGateStatus, Portfolio, ProfitabilityStatus, StrategyConfig, Trade } from "./api";
import { buildEquityHistoryFromTrades, enrichProfitabilityStatus } from "./profitability";
import { resolveBackendHttpUrl } from "./production-backend";

export function backendBase(): string {
  return resolveBackendHttpUrl();
}

async function fetchBackendJson<T>(path: string): Promise<T> {
  const res = await fetch(`${backendBase()}/api/${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`backend ${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

/** Active-bot gate: excludes paused bots even when Render has not deployed gate logic. */
export async function fetchActiveGateStatus(): Promise<ProfitabilityStatus> {
  const [profitability, strategies, portfolios, trades, perBotRes] = await Promise.all([
    fetchBackendJson<ProfitabilityStatus>("profitability"),
    fetchBackendJson<StrategyConfig[]>("strategies"),
    fetchBackendJson<Portfolio[]>("portfolios"),
    fetchBackendJson<Trade[]>("trades?limit=200"),
    fetchBackendJson<{ bots: Record<string, PerBotGateStatus> }>("gate/per-bot").catch(() => ({ bots: {} })),
  ]);
  const enriched =
    enrichProfitabilityStatus(profitability, trades, portfolios, strategies) ?? profitability;
  if (perBotRes.bots && Object.keys(perBotRes.bots).length > 0) {
    enriched.per_bot = perBotRes.bots;
  }
  return enriched;
}

/** Equity curve from trades when backend /equity-history is not deployed yet. */
export async function fetchEquityHistory(): Promise<EquityHistoryPoint[]> {
  try {
    const direct = await fetchBackendJson<EquityHistoryPoint[]>("equity-history");
    if (direct.length > 0) return direct;
  } catch {
    /* fall through */
  }
  const trades = await fetchBackendJson<Trade[]>("trades?limit=500");
  return buildEquityHistoryFromTrades(trades.filter((t) => t.action === "sell"));
}
