"use client";

import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { VerificationSnapshot } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

export function VerificationPnLChart({ snapshots }: { snapshots: VerificationSnapshot[] }) {
  if (!snapshots.length) return null;

  const points = [...snapshots]
    .sort((a, b) => a.verification_day - b.verification_day)
    .map((s) => ({
      day: `D${s.verification_day}`,
      pnl: Math.round(s.total_pnl * 100) / 100,
      trades: s.total_trades,
      wr: Math.round(s.win_rate * 1000) / 10,
    }));

  return (
    <div className="mt-3 h-36">
      <p className="text-[10px] text-gray-500 mb-2 uppercase tracking-wide">Verification PnL trend</p>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <XAxis dataKey="day" tick={{ fill: "#6b7280", fontSize: 10 }} axisLine={false} tickLine={false} />
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
            formatter={(value: number, name: string) => {
              if (name === "pnl") return [formatCurrency(value), "PnL"];
              if (name === "wr") return [`${value}%`, "Win rate"];
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
