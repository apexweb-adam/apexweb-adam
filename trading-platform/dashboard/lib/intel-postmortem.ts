/** Detect intel sources referenced in post-mortem root causes and lessons. */

export type IntelPostMortemSource = {
  id: string;
  label: string;
  className: string;
};

const INTEL_POSTMORTEM_SOURCES: { id: string; label: string; className: string; pattern: RegExp }[] = [
  { id: "political", label: "Political", className: "bg-purple-500/15 text-purple-300 border-purple-500/30", pattern: /political|geopolitical|tariff|fed\/election/i },
  { id: "news", label: "News", className: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30", pattern: /newsapi|news headline|breaking news/i },
  { id: "tiktok", label: "TikTok", className: "bg-pink-500/15 text-pink-300 border-pink-500/30", pattern: /tiktok/i },
  { id: "reddit", label: "Reddit", className: "bg-orange-500/15 text-orange-300 border-orange-500/30", pattern: /reddit|wsb/i },
  { id: "x", label: "X", className: "bg-sky-500/15 text-sky-300 border-sky-500/30", pattern: /x\/twitter|twitter/i },
  { id: "youtube", label: "YouTube", className: "bg-red-500/15 text-red-300 border-red-500/30", pattern: /youtube/i },
  { id: "tradingview", label: "TradingView", className: "bg-blue-500/15 text-blue-300 border-blue-500/30", pattern: /tradingview/i },
  { id: "fomo", label: "fomo", className: "bg-amber-500/15 text-amber-300 border-amber-500/30", pattern: /fomo/i },
  { id: "polymarket", label: "Polymarket", className: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30", pattern: /polymarket/i },
];

export function detectIntelPostMortemSources(
  rootCause: string,
  lessonsLearned?: string
): IntelPostMortemSource[] {
  const blob = `${rootCause} ${lessonsLearned ?? ""}`;
  return INTEL_POSTMORTEM_SOURCES.filter((source) => source.pattern.test(blob)).map(
    ({ id, label, className }) => ({ id, label, className })
  );
}

const INTEL_SOURCE_TYPE_ALIASES: Record<string, string> = {
  newsapi: "news",
  polymarket_account: "polymarket",
  wallet_tracker: "fomo",
};

/** Map content-study / intel source_type values to badge styling. */
export function intelSourceBadge(sourceType: string): IntelPostMortemSource | null {
  const normalized = sourceType.toLowerCase();
  const id = INTEL_SOURCE_TYPE_ALIASES[normalized] ?? normalized;
  const match = INTEL_POSTMORTEM_SOURCES.find((source) => source.id === id);
  if (!match) {
    return null;
  }
  const { id: badgeId, label, className } = match;
  return { id: badgeId, label, className };
}
