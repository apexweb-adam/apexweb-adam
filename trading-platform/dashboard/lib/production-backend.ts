/** Production backend used when env vars and /api/config are unavailable. */
export const PRODUCTION_BACKEND_HTTP = "https://apex-trading-backend.onrender.com";
export const PRODUCTION_BACKEND_WS = "wss://apex-trading-backend.onrender.com";

export function resolveBackendHttpUrl(): string {
  return (
    process.env.BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    PRODUCTION_BACKEND_HTTP
  ).replace(/\/$/, "");
}

export function resolveBackendWsUrl(httpUrl?: string): string {
  const explicit =
    process.env.BACKEND_WS_URL || process.env.NEXT_PUBLIC_WS_URL || "";
  if (explicit) return explicit.replace(/\/$/, "");

  const http = (httpUrl || resolveBackendHttpUrl()).replace(/\/$/, "");
  return http.replace(/^http:\/\//, "ws://").replace(/^https:\/\//, "wss://");
}
