"use client";

import type { IntelligenceSource, PlatformStatus } from "@/lib/api";
import { intelFeedSourceBadge } from "@/lib/intel-postmortem";
import { cn } from "@/lib/utils";

type RowProps = {
  sourceKey: string;
  label: string;
  detail?: string;
  status?: string;
  items?: number;
};

function IntelSourceRow({ sourceKey, label, detail, status, items }: RowProps) {
  const badge = intelFeedSourceBadge(sourceKey);
  return (
    <div className="flex items-start justify-between gap-2 py-1.5 border-b border-apex-border/50 last:border-0">
      <div className="min-w-0">
        <span
          className={cn(
            "text-[10px] px-1.5 py-0.5 rounded border font-medium",
            badge.className
          )}
        >
          {label}
        </span>
        {detail ? <p className="mt-1 text-[10px] text-gray-500">{detail}</p> : null}
      </div>
      <div className="text-right shrink-0">
        {status ? (
          <span
            className={cn(
              "text-[10px] px-2 py-0.5 rounded-full uppercase font-medium",
              status === "active"
                ? "bg-apex-green/10 text-apex-green"
                : status === "degraded"
                  ? "bg-apex-gold/10 text-apex-gold"
                  : status === "optional" || status === "pending"
                    ? "bg-gray-800 text-gray-500"
                    : "bg-gray-800 text-gray-500"
            )}
          >
            {status}
          </span>
        ) : null}
        {items != null ? (
          <p className="text-[10px] text-gray-600 mt-0.5">{items} items</p>
        ) : null}
      </div>
    </div>
  );
}

function lookupSource(
  sources: IntelligenceSource[] | null | undefined,
  name: string
): IntelligenceSource | undefined {
  return sources?.find((row) => row.source === name);
}

export function MultiSourceIntelCard({
  integrations,
  sources,
}: {
  integrations?: PlatformStatus["integrations"];
  sources?: IntelligenceSource[] | null;
}) {
  if (!integrations && !sources?.length) {
    return null;
  }

  const newsapi = lookupSource(sources, "newsapi");
  const news = lookupSource(sources, "news");
  const x = lookupSource(sources, "x");
  const reddit = lookupSource(sources, "reddit");
  const political = lookupSource(sources, "political");
  const tiktok = lookupSource(sources, "tiktok");
  const youtube = lookupSource(sources, "youtube");

  const xMode = integrations?.x_intel_collection_mode;
  const xDetail = integrations?.x_intel_keyless
    ? "Google News RSS (keyless fallback)"
    : xMode === "newsapi"
      ? "NewsAPI social fallback"
      : integrations?.twitter_x
        ? "X API bearer token"
        : "Scanner active — set TWITTER_BEARER_TOKEN or use keyless RSS";

  const newsDetail = integrations?.newsapi
    ? "NewsAPI headlines feed strategy + content study"
    : "General news RSS active — set NEWSAPI_KEY for richer headlines";

  const redditDetail = integrations?.reddit_oauth
    ? "OAuth API polling"
    : reddit?.oauth_configured === false
      ? "RSS fallback (set REDDIT_CLIENT_ID + SECRET for OAuth)"
      : "Subreddit scanner";

  return (
    <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
      <p className="text-apex-gold font-medium mb-2">Multi-source intel (news · X · social · political)</p>
      <div className="space-y-0">
        <IntelSourceRow
          sourceKey="newsapi"
          label="News"
          detail={newsDetail}
          status={newsapi?.status ?? news?.status}
          items={(newsapi?.items_collected ?? 0) + (news?.items_collected ?? 0) || undefined}
        />
        <IntelSourceRow
          sourceKey="x"
          label="X / Twitter"
          detail={xDetail}
          status={x?.status}
          items={x?.items_collected}
        />
        <IntelSourceRow
          sourceKey="reddit"
          label="Reddit"
          detail={redditDetail}
          status={reddit?.status}
          items={reddit?.items_collected}
        />
        <IntelSourceRow
          sourceKey="political"
          label="Political"
          detail="Tariffs, Fed, elections — routed to commodities/stocks/polymarket bots"
          status={political?.status ?? "active"}
          items={political?.items_collected}
        />
        <IntelSourceRow
          sourceKey="tiktok"
          label="TikTok"
          detail="Social hype scanner — tightens entries when viral sentiment repeats in losses"
          status={tiktok?.status}
          items={tiktok?.items_collected}
        />
        <IntelSourceRow
          sourceKey="youtube"
          label="YouTube"
          detail="Hourly content study + headline scanner for strategy takeaways"
          status={youtube?.status}
          items={youtube?.items_collected}
        />
      </div>
    </div>
  );
}
