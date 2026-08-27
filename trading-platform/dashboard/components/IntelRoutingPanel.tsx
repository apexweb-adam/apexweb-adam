"use client";

import type { IntelRouting } from "@/lib/api";
import { botLabel, cn } from "@/lib/utils";

const BOT_ORDER = ["crypto", "stocks_futures", "commodities", "polymarket"];

export function IntelRoutingPanel({ routing }: { routing: IntelRouting | null }) {
  if (!routing) {
    return <p className="text-sm text-gray-500 py-4">Loading intel routing...</p>;
  }

  const weights = routing.bot_source_weights;

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        Per-bot source weights — higher values mean stronger influence on trade sentiment.
      </p>
      {BOT_ORDER.map((bot) => {
        const srcWeights = weights[bot];
        if (!srcWeights) return null;
        const sorted = Object.entries(srcWeights).sort((a, b) => b[1] - a[1]);
        return (
          <div key={bot} className="p-3 rounded-lg bg-apex-dark border border-apex-border">
            <p className="text-sm font-medium text-white mb-2">{botLabel(bot)}</p>
            <div className="flex flex-wrap gap-1.5">
              {sorted.map(([source, w]) => (
                <span
                  key={source}
                  className={cn(
                    "text-[10px] px-2 py-0.5 rounded-full font-mono",
                    w >= 1.2
                      ? "bg-apex-gold/15 text-apex-gold border border-apex-gold/30"
                      : w >= 0.8
                        ? "bg-apex-purple/15 text-apex-purple border border-apex-purple/30"
                        : "bg-apex-border text-gray-500"
                  )}
                >
                  {source} ×{w.toFixed(2)}
                </span>
              ))}
            </div>
          </div>
        );
      })}
      {routing.political_event_types.length > 0 && (
        <div className="p-3 rounded-lg bg-apex-dark border border-apex-border">
          <p className="text-sm font-medium text-white mb-2">Political event routing</p>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {routing.political_event_types.map((ev) => (
              <div key={ev.type} className="text-[10px] text-gray-400 flex gap-2">
                <span className="text-apex-gold uppercase shrink-0">{ev.type}</span>
                <span>→ {ev.bots.map(botLabel).join(", ")}</span>
                <span className="text-gray-600">({ev.assets.join(", ")})</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
