/** Bump when dashboard features change — compared in /api/config for stale Vercel detection. */
export const DASHBOARD_BUNDLE_REVISION = "2026-08-27-r12";

/** Verified preview when production -flame bundle is stale (matches backend deploy_status defaults). */
export const VERIFIED_PREVIEW_URL =
  "https://apex-trading-dashboard-796165b96-apexweb-adams-projects.vercel.app";
export const VERIFIED_PROMOTE_DEPLOYMENT_ID = "dpl_7nvzwTX8dwLLDDDBVHnUVWdvNs78";

export const DASHBOARD_FEATURES = {
  activeGate: true,
  clientGateEnrichment: true,
  proxyGateEnrichment: true,
  intelRouting: true,
  equityChart: true,
} as const;
