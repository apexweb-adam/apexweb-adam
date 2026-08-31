export const RENDER_BACKEND_DASHBOARD_URL =
  "https://dashboard.render.com/web/srv-da848ms9v7es739k38jg";

export type BackendSuspension = {
  suspended: true;
  reason: "billing" | "unknown";
  message: string;
  render_dashboard_url: string;
  recovery_steps: string[];
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

export function buildBackendSuspensionPayload(
  reason: "billing" | "unknown" = "billing"
): BackendSuspension {
  return {
    suspended: true,
    reason,
    message:
      reason === "billing"
        ? "Render backend suspended by billing — bots, intel, and CRM data are offline."
        : "Render backend is suspended — platform data is unavailable.",
    render_dashboard_url: RENDER_BACKEND_DASHBOARD_URL,
    recovery_steps: [
      "Open the Render dashboard and resolve billing (payment method / upgrade from free).",
      "Resume apex-trading-backend manually (API resume does not work for billing suspension).",
      "Run: bash trading-platform/scripts/recover-render-billing.sh",
      "If US open was missed with queued symbols, deploy r450+ before the 270-minute outage grace expires.",
    ],
  };
}
