import { EXPECTED_PLATFORM_REVISION } from "./deploy-health";

export const RENDER_BACKEND_DASHBOARD_URL =
  "https://dashboard.render.com/web/srv-da848ms9v7es739k38jg";

export type OutageRecoveryBot = {
  bot_type: string;
  label: string;
  action: string;
  verify_script?: string;
  held_symbols?: string[];
};

export type BackendSuspension = {
  suspended: true;
  reason: "billing" | "unknown";
  message: string;
  render_dashboard_url: string;
  recovery_steps: string[];
  platform_outage_grace_minutes_remaining?: number | null;
  platform_outage_grace_deadline_utc?: string | null;
  us_cash_session_catchup_minutes_remaining?: number | null;
  post_grace_catchup_active?: boolean;
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
      action: "Burst scan + auto-entry for open-ready symbols (prep state preserved)",
      verify_script: "verify-us-stocks-post-open.sh --watch 120",
      held_symbols: ["AAPL"],
    },
    {
      bot_type: "commodities",
      label: "Commodities / CME",
      action: "TV refresh + burst scan for held futures and forex",
      verify_script: "verify-cme-post-open.sh --watch 90",
      held_symbols: ["EURUSD=X", "GC=F", "HG=F"],
    },
    {
      bot_type: "crypto",
      label: "Crypto 24/7",
      action: "Immediate held-position scan on startup",
      verify_script: "verify-crypto-held.sh --watch 90",
    },
    {
      bot_type: "learning",
      label: "Learning loop",
      action: "Post-mortems, content study, intel pattern alerts, strategy adaptation",
      verify_script: "verify-crm-learning.sh --strict",
    },
  ];
}

/** Minutes left in Monday US cash session catch-up window (until 21:00 UTC), or null if N/A. */
export function usCashSessionCatchupMinutesRemaining(now = new Date()): number | null {
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
  const sessionEnd = Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
    21,
    0,
    0,
    0
  );
  const nowMs = now.getTime();
  if (nowMs < openAt) return null;
  if (nowMs >= sessionEnd) return 0;
  return Math.max(0, Math.floor((sessionEnd - nowMs) / 60000));
}

/** True when Monday extended grace expired but US cash session catch-up window is still open. */
export function isPostGraceCatchupActive(now = new Date()): boolean {
  const graceRemaining = platformOutageGraceMinutesRemaining(now);
  const catchupRemaining = usCashSessionCatchupMinutesRemaining(now);
  return graceRemaining === 0 && catchupRemaining !== null && catchupRemaining > 0;
}

export function buildBackendSuspensionPayload(
  reason: "billing" | "unknown" = "billing"
): BackendSuspension {
  const graceRemaining = platformOutageGraceMinutesRemaining();
  const catchupRemaining = usCashSessionCatchupMinutesRemaining();
  const postGraceCatchupActive = isPostGraceCatchupActive();
  const graceNote =
    graceRemaining !== null && graceRemaining > 0
      ? `Platform outage grace: ~${graceRemaining} min left for extended burst window (deploy ${EXPECTED_PLATFORM_REVISION}). Post-outage startup still forces open-ready scan if prep state preserved.`
      : graceRemaining === 0 && catchupRemaining !== null && catchupRemaining > 0
        ? `Extended burst grace expired — ~${catchupRemaining} min until US cash close. Post-outage startup still forces open-ready scan if prep state preserved (deploy ${EXPECTED_PLATFORM_REVISION}).`
        : graceRemaining === 0
          ? "Extended burst grace expired — post-outage startup still forces open-ready scan if prep state preserved."
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
      "Or verify all bots: bash trading-platform/scripts/verify-post-outage-recovery.sh --watch 90",
      "Verify learning loop: bash trading-platform/scripts/verify-crm-learning.sh --strict",
      "Verify WebSocket live CRM: bash trading-platform/scripts/verify-ws-live.sh --strict",
      `After resume, confirm outage_recovery_scan then burst_scan (deploy ${EXPECTED_PLATFORM_REVISION}).`,
    ],
    us_cash_session_catchup_minutes_remaining: catchupRemaining,
    post_grace_catchup_active: postGraceCatchupActive,
  };
}
