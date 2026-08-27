import type { Portfolio, ProfitabilityStatus, StrategyConfig, Trade } from "./api";
import { enrichProfitabilityStatus } from "./profitability";

export function backendBase(): string {
  return (
    process.env.BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  ).replace(/\/$/, "");
}

async function fetchBackendJson<T>(path: string): Promise<T> {
  const res = await fetch(`${backendBase()}/api/${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`backend ${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

/** Active-bot gate: excludes paused bots even when Render has not deployed gate logic. */
export async function fetchActiveGateStatus(): Promise<ProfitabilityStatus> {
  const [profitability, strategies, portfolios, trades] = await Promise.all([
    fetchBackendJson<ProfitabilityStatus>("profitability"),
    fetchBackendJson<StrategyConfig[]>("strategies"),
    fetchBackendJson<Portfolio[]>("portfolios"),
    fetchBackendJson<Trade[]>("trades?limit=200"),
  ]);
  return enrichProfitabilityStatus(profitability, trades, portfolios, strategies) ?? profitability;
}
