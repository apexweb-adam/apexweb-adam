"use client";

import { Bot } from "lucide-react";

import type { Bot as BotRow, BotSessions, ProfitabilityStatus } from "@/lib/api";
import { botLabel, cn, formatCurrency, formatSessionCountdown, pnlColor } from "@/lib/utils";

const CORE_BOT_TYPES = ["crypto", "stocks_futures", "commodities"] as const;

const CORE_BOT_SCHEDULES: Record<(typeof CORE_BOT_TYPES)[number], string> = {
  crypto: "24/7 autonomous paper trading",
  stocks_futures: "US cash session day-trading",
  commodities: "CME futures 24/7",
};

function sessionModeLabel(mode: string | undefined, inSession: boolean | undefined): string {
  if (!mode) return inSession ? "active" : "idle";
  switch (mode) {
    case "entries":
      return "scanning";
    case "winddown":
    case "winddown_only":
      return "winddown";
    case "pre_session":
      return "pre-session";
    case "outside_session":
      return "outside session";
    case "weekend_closed":
      return "weekend closed";
    default:
      return mode.replace(/_/g, " ");
  }
}

export function CoreMarketBotsCard({
  bots,
  botSessions,
  profitability,
  paperTradingOnly,
  backendOffline,
}: {
  bots: BotRow[];
  botSessions?: BotSessions | null;
  profitability?: ProfitabilityStatus | null;
  paperTradingOnly?: boolean;
  backendOffline?: boolean;
}) {
  const botMap = new Map(bots.map((row) => [row.bot_type, row]));

  return (
    <div className="space-y-3">
      {backendOffline ? (
        <p className="text-[10px] text-apex-red border border-apex-red/30 bg-apex-red/10 rounded px-2 py-1.5">
          Backend offline — bot scans, intel, and learning are paused until Render billing is restored.
          Last snapshot below may be stale.
        </p>
      ) : null}
      <p className="text-[10px] text-gray-500">
        {paperTradingOnly === false
          ? "Live trading enabled — profitability gate bypassed."
          : "Paper-only until profitability verification passes — live capital stays blocked."}
        {profitability?.verification_day != null && profitability.verification_day > 0 && (
          <span className="text-apex-gold">
            {" "}
            Verification day {profitability.verification_day}
            {profitability.verification_days_remaining != null
              ? ` (${profitability.verification_days_remaining} remaining)`
              : ""}
            .
          </span>
        )}
      </p>
      {CORE_BOT_TYPES.map((botType) => {
        const bot = botMap.get(botType);
        const session = botSessions?.[botType];
        const perBot = profitability?.per_bot?.[botType];
        const countdown =
          session && !session.in_session
            ? formatSessionCountdown(session.minutes_until_open)
            : session?.in_session && session.minutes_until_close != null
              ? `closes in ${formatSessionCountdown(session.minutes_until_close)}`
              : null;

        return (
          <div
            key={botType}
            className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <Bot size={14} className="text-apex-gold shrink-0" />
                  <span className="text-sm font-medium text-white">{botLabel(botType)}</span>
                  <span
                    className={cn(
                      "text-[10px] px-2 py-0.5 rounded-full uppercase font-medium",
                      bot?.status === "scanning"
                        ? "bg-apex-green/10 text-apex-green"
                        : bot?.status === "trading"
                          ? "bg-apex-blue/10 text-apex-blue"
                          : "bg-gray-800 text-gray-500"
                    )}
                  >
                    {bot?.status ?? "offline"}
                  </span>
                  {session && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-apex-purple/10 text-apex-purple">
                      {sessionModeLabel(session.mode, session.in_session)}
                    </span>
                  )}
                  {perBot?.paused && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400">
                      gate paused
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-gray-500 mt-1">{CORE_BOT_SCHEDULES[botType]}</p>
                {countdown && (
                  <p className="text-[10px] text-apex-gold mt-0.5">{countdown}</p>
                )}
                {bot?.last_action && (
                  <p className="text-[10px] text-gray-600 mt-1 truncate">{bot.last_action}</p>
                )}
              </div>
              <div className="text-right shrink-0 text-[10px]">
                <p className="text-gray-400">{bot?.trades_today ?? 0} trades today</p>
                <p className={cn("font-medium", pnlColor(bot?.pnl_today ?? 0))}>
                  {formatCurrency(bot?.pnl_today ?? 0)}
                </p>
                {perBot && (
                  <p className="text-gray-600 mt-0.5">
                    {perBot.total_trades} total · {Math.round(perBot.win_rate * 100)}% WR
                  </p>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
