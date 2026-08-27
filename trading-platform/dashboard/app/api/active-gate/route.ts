import { NextResponse } from "next/server";
import { fetchActiveGateStatus } from "@/lib/active-gate";

export const dynamic = "force-dynamic";

/** Standalone active-bot profitability gate (works without Render deploy). */
export async function GET() {
  try {
    const gate = await fetchActiveGateStatus();
    return NextResponse.json({
      paused_bots: gate.paused_bots ?? [],
      active_bots: {
        total_trades: gate.total_trades,
        win_rate: gate.win_rate,
        profit_factor: gate.profit_factor,
        total_pnl: gate.total_pnl,
      },
      aggregate: gate.aggregate ?? {
        total_trades: gate.total_trades,
        win_rate: gate.win_rate,
        profit_factor: gate.profit_factor,
        total_pnl: gate.total_pnl,
      },
      verification_day: gate.verification_day,
      verification_days_remaining: gate.verification_days_remaining,
      live_trading_ready: gate.live_trading_ready,
      checks: gate.checks,
      recommendation: gate.recommendation,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "active gate failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
