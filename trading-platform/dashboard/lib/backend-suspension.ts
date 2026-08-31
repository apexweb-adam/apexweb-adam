import { EXPECTED_PLATFORM_REVISION } from "./deploy-health";

export const RENDER_BACKEND_DASHBOARD_URL =
  "https://dashboard.render.com/web/srv-da848ms9v7es739k38jg";

export type OutageRecoveryBot = {
  bot_type: string;
  label: string;
  action: string;
};

export type BackendSuspension = {
  suspended: true;
  reason: "billing" | "unknown";
  message: string;
  render_dashboard_url: string;
  recovery_steps: string[];
  platform_outage_grace_minutes_remaining?: number | null;
  platform_outage_grace_deadline_utc?: string | null;
  expected_platform_revision?: string;
  recovery_bots?: OutageRecoveryBot[];
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

/** ISO UTC deadline for Monday platform-outage grace, or null if N/A / expired. */
export function platformOutageGraceDeadlineUtc(now = new Date()): string | null {
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
  if (nowMs < openAt || nowMs > extEnd) return null;
  return new Date(extEnd).toISOString();
}

export function outageRecoveryBots(): OutageRecoveryBot[] {
  return [
    {
      bot_type: "stocks_futures",
      label: "US stocks",
      action: "Burst scan + auto-entry for open-ready symbols (e.g. AAPL)",
    },
    {
      bot_type: "commodities",
      label: "Commodities / CME",
      action: "TV refresh + burst scan for held futures and forex",
    },
    {
      bot_type: "crypto",
      label: "Crypto 24/7",
      action: "Immediate held-position scan on startup",
    },
  ];
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
    platform_outage_grace_deadline_utc: platformOutageGraceDeadlineUtc(),
    expected_platform_revision: EXPECTED_PLATFORM_REVISION,
    recovery_bots: outageRecoveryBots(),
    recovery_steps: [
      "Open the Render dashboard and resolve billing (payment method / upgrade from free).",
      "Resume apex-trading-backend manually (API resume does not work for billing suspension).",
      "Run: bash trading-platform/scripts/recover-render-billing.sh",
      graceNote,
      `After resume, confirm outage_recovery_scan then burst_scan in the US stocks open checklist (deploy ${EXPECTED_PLATFORM_REVISION}).`,
    ],
  };
}
