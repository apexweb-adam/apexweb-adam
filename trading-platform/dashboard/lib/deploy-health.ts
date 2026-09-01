/** Bump when dashboard features change — compared in /api/config for stale Vercel detection. */
export const DASHBOARD_BUNDLE_REVISION = "2026-08-29-r138";

/** Fallback scheduler labels when /api/status is unreachable (matches backend platform_status). */
export const DEFAULT_PLATFORM_SCHEDULER: Record<string, string> = {
  intelligence_scan: "every 5 min",
  content_study: "every 1 hour",
  risk_migration: "every 15 min",
  redeploy_check: "every 1 hour",
  stocks_pre_session_prep:
    "13:00 UTC Mon-Fri + Sat/Sun 14:00 + every 15 min (72h window when trade-count nudge)",
  commodities_pre_session_prep:
    "22:30 UTC Sun + every 15 min (72h window when graduation nudge)",
  held_positions_tv_refresh: "every 30 min for open gate positions",
  daily_review: "22:00 UTC",
  daily_review_refresh: "every 4 hours",
  verification_snapshot: "23:00 UTC",
};

/** Matches backend EXPECTED_PLATFORM_REVISION — update when backend revision bumps. */
export const EXPECTED_PLATFORM_REVISION = "2026-08-29-r467";

/** Verified preview when production -flame bundle is stale (matches backend VERIFIED_DASHBOARD_URL). */
export const VERIFIED_PREVIEW_URL =
  "https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app";
export const VERIFIED_PROMOTE_DEPLOYMENT_ID = "dpl_4fzZAaUaL2mBCEv1EewqeGci2A5a";

export const DASHBOARD_FEATURES = {
  activeGate: true,
  clientGateEnrichment: true,
  proxyGateEnrichment: true,
  intelRouting: true,
  equityChart: true,
  verificationProgress: true,
  realtimeGate: true,
  realtimeLearning: true,
  realtimeIntel: true,
  realtimeStrategy: true,
  realtimeVerification: true,
  sessionOpenChecklists: true,
  cmeDeployWindow: true,
  intelPostMortemTags: true,
} as const;
