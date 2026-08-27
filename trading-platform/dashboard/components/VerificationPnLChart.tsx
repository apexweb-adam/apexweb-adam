"use client";

import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EquityHistoryPoint, VerificationSnapshot } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

type ChartPoint = {
  label: string;
  pnl: number;
  daily?: number;
};

function buildPoints(
  snapshots: VerificationSnapshot[],
  equityHistory: EquityHistoryPoint[]
): ChartPoint[] {
  if (snapshots.length >= 2) {
    return [...snapshots]
      .sort((a, b) => a.verification_day - b.verification_day)
      .map((s) => ({
        label: `D${s.verification_day}`,
        pnl: Math.round(s.total_pnl * 100) / 100,
      }));
  }
  if (equityHistory.length > 0) {
    return equityHistory.map((p) => ({
      label: p.date.slice(5),
      pnl: p.cumulative_pnl,
      daily: p.daily_pnl,
    }));
  }
  if (snapshots.length === 1) {
    const s = snapshots[0];
    return [{ label: `D${s.verification_day}`, pnl: Math.round(s.total_pnl * 100) / 100 }];
  }
  return [];
}

export function VerificationPnLChart({
  snapshots,
  equityHistory = [],
}: {
  snapshots: VerificationSnapshot[];
  equityHistory?: EquityHistoryPoint[];
}) {
  const points = buildPoints(snapshots, equityHistory);
  if (!points.length) return null;

  const title =
    snapshots.length >= 2
      ? "Verification PnL trend"
      : equityHistory.length > 0
        ? "Daily equity curve (realized PnL)"
        : "Verification PnL";

  return (
    <div className="mt-3 h-36">
      <p className="text-[10px] text-gray-500 mb-2 uppercase tracking-wide">{title}</p>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <XAxis dataKey="label" tick={{ fill: "#6b7280", fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis
            tick={{ fill: "#6b7280", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={48}
            tickFormatter={(v) => `$${v}`}
          />
          <Tooltip
            contentStyle={{
              background: "#1a1a2e",
              border: "1px solid #2a2a3e",
              borderRadius: 8,
              fontSize: 11,
            }}
            formatter={(value: number, name: string, props: { payload?: ChartPoint }) => {
              if (name === "pnl") {
                const daily = props.payload?.daily;
                if (daily != null) {
                  return [formatCurrency(value) + ` (day ${formatCurrency(daily)})`, "Cumulative"];
                }
                return [formatCurrency(value), "PnL"];
              }
              return [value, name];
            }}
            labelFormatter={(label) => `${label}`}
          />
          <Line
            type="monotone"
            dataKey="pnl"
            stroke="#d4af37"
            strokeWidth={2}
            dot={{ fill: "#d4af37", r: 3 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
