/** Bump when dashboard features change — compared in /api/config for stale Vercel detection. */
export const DASHBOARD_BUNDLE_REVISION = "2026-08-27-r9";

export const DASHBOARD_FEATURES = {
  activeGate: true,
  clientGateEnrichment: true,
  proxyGateEnrichment: true,
  intelRouting: true,
  equityChart: true,
} as const;
