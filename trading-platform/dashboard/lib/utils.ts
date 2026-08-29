import { clsx } from "clsx";

export function cn(...inputs: (string | boolean | undefined)[]) {
  return clsx(inputs);
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(value);
}

export function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString();
}

export function botLabel(type: string): string {
  const labels: Record<string, string> = {
    crypto: "Crypto 24/7",
    stocks_futures: "Stocks & Futures",
    commodities: "Commodities 24/7",
    polymarket: "Polymarket Predictions 24/7",
  };
  return labels[type] || type;
}

const SCAN_BLOCKER_LABELS: Record<string, string> = {
  weekend_futures_closed: "CME closed",
  stocks_session_closed: "US session closed",
  gate_skip: "gate skip",
  weekend_spot_blocked: "weekend spot blocked",
  weekend_forex_blocked: "forex closed",
};

export function formatScanBlocker(blocker: string): string {
  return SCAN_BLOCKER_LABELS[blocker] ?? blocker.replace(/_/g, " ");
}

export function formatScanBlockers(blockers: string[], limit = 2): string {
  return blockers.slice(0, limit).map(formatScanBlocker).join(", ");
}

export function sentimentColor(score: number): string {
  if (score > 0.2) return "text-apex-green";
  if (score < -0.2) return "text-apex-red";
  return "text-gray-400";
}

export function pnlColor(value: number): string {
  if (value > 0) return "text-apex-green";
  if (value < 0) return "text-apex-red";
  return "text-gray-400";
}
