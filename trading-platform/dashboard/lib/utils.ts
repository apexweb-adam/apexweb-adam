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
