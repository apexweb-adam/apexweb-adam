/** Bump when dashboard features change — compared in /api/config for stale Vercel detection. */
export const DASHBOARD_BUNDLE_REVISION = "2026-08-28-r25";

/** Verified preview when production -flame bundle is stale (matches backend deploy_status defaults). */
export const VERIFIED_PREVIEW_URL =
  "https://apex-trading-dashboard-73nruanbo-apexweb-adams-projects.vercel.app";
export const VERIFIED_PROMOTE_DEPLOYMENT_ID = "dpl_29H1cYhLuLb1wN7L3HJD9yizZ8pL";

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
} as const;
