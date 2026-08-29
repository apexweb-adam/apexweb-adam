/** Bump when dashboard features change — compared in /api/config for stale Vercel detection. */
export const DASHBOARD_BUNDLE_REVISION = "2026-08-29-r75";

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
} as const;
