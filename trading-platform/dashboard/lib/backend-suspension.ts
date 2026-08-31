import { EXPECTED_PLATFORM_REVISION } from "./deploy-health";

export const RENDER_BACKEND_DASHBOARD_URL =
  "https://dashboard.render.com/web/srv-da848ms9v7es739k38jg";

export type BackendSuspension = {
  suspended: true;
  reason: "billing" | "unknown";
  message: string;
  render_dashboard_url: string;
  recovery_steps: string[];
  platform_outage_grace_minutes_remaining?: number | null;
};

export function isBackendSuspendedBody(
  status: number,
  body: string,
  contentType?: string | null
): boolean {
  if (status !== 503) return false;
  if (body.includes("Service Suspended")) return true;
  if ((contentType || "").includes("text/html") && body.includes("suspended")) return true;
  return false;
}

/** Minutes left in Monday US platform-outage grace (270 min from 13:30 UTC), or null if N/A. */
export function platformOutageGraceMinutesRemaining(now = new Date()): number | null {
  if (now.getUTCDay() !== 1) return null;
  const openAt = Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
    13,
    30,
    0,
    0
  );
  const extEnd = openAt + 270 * 60 * 1000;
  const nowMs = now.getTime();
  if (nowMs < openAt) return null;
  if (nowMs > extEnd) return 0;
  return Math.max(0, Math.floor((extEnd - nowMs) / 60000));
}

export function buildBackendSuspensionPayload(
  reason: "billing" | "unknown" = "billing"
): BackendSuspension {
  const graceRemaining = platformOutageGraceMinutesRemaining();
  const graceNote =
    graceRemaining !== null && graceRemaining > 0
      ? `Platform outage grace: ~${graceRemaining} min left for AAPL catch-up (deploy ${EXPECTED_PLATFORM_REVISION}).`
      : graceRemaining === 0
        ? "Platform outage grace expired — only normal scan intervals after resume."
        : `If US open was missed with queued symbols, deploy ${EXPECTED_PLATFORM_REVISION} before the 270-minute outage grace expires.`;

  return {
    suspended: true,
    reason,
    message:
      reason === "billing"
        ? "Render backend suspended by billing — bots, intel, and CRM data are offline."
        : "Render backend is suspended — platform data is unavailable.",
    render_dashboard_url: RENDER_BACKEND_DASHBOARD_URL,
    platform_outage_grace_minutes_remaining: graceRemaining,
    recovery_steps: [
      "Open the Render dashboard and resolve billing (payment method / upgrade from free).",
      "Resume apex-trading-backend manually (API resume does not work for billing suspension).",
      "Run: bash trading-platform/scripts/recover-render-billing.sh",
      graceNote,
    ],
  };
}
