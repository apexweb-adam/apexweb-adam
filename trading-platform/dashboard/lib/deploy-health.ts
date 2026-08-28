/** Bump when dashboard features change — compared in /api/config for stale Vercel detection. */
export const DASHBOARD_BUNDLE_REVISION = "2026-08-27-r16";

/** Verified preview when production -flame bundle is stale (matches backend deploy_status defaults). */
export const VERIFIED_PREVIEW_URL =
  "https://apex-trading-dashboard-39gtc4hgx-apexweb-adams-projects.vercel.app";
export const VERIFIED_PROMOTE_DEPLOYMENT_ID = "dpl_GpWprv2SKRA78p46JEXZtRUX4oCQ";

export const DASHBOARD_FEATURES = {
  activeGate: true,
  clientGateEnrichment: true,
  proxyGateEnrichment: true,
  intelRouting: true,
  equityChart: true,
  verificationProgress: true,
} as const;
