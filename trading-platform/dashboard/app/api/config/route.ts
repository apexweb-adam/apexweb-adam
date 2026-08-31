import { NextResponse } from "next/server";
import { DASHBOARD_BUNDLE_REVISION, DASHBOARD_FEATURES } from "@/lib/deploy-health";
import { resolveBackendHttpUrl, resolveBackendWsUrl } from "@/lib/production-backend";
import {
  buildBackendSuspensionPayload,
  isBackendSuspendedBody,
} from "@/lib/backend-suspension";

export const dynamic = "force-dynamic";

function backendHttpUrl(): string {
  return resolveBackendHttpUrl();
}

function backendWsUrl(): string {
  return resolveBackendWsUrl(backendHttpUrl());
}

async function probeBackendHealth(base: string) {
  try {
    const res = await fetch(`${base}/api/health`, { cache: "no-store" });
    const body = await res.text();
    if (isBackendSuspendedBody(res.status, body, res.headers.get("content-type"))) {
      const payload = buildBackendSuspensionPayload("billing");
      return {
        reachable: false,
        suspended: payload.suspended,
        reason: payload.reason,
        message: payload.message,
        render_dashboard_url: payload.render_dashboard_url,
        recovery_steps: payload.recovery_steps,
        platform_outage_grace_minutes_remaining:
          payload.platform_outage_grace_minutes_remaining,
        platform_outage_grace_deadline_utc: payload.platform_outage_grace_deadline_utc,
        expected_platform_revision: payload.expected_platform_revision,
        recovery_bots: payload.recovery_bots,
      };
    }
    return {
      reachable: res.ok,
      suspended: false,
    };
  } catch {
    return {
      reachable: false,
      suspended: false,
    };
  }
}

export async function GET() {
  let mainCommit: string | null = null;
  try {
    const res = await fetch(
      "https://api.github.com/repos/apexweb-adam/apexweb-adam/commits/main",
      { cache: "no-store" }
    );
    if (res.ok) {
      const data = (await res.json()) as { sha?: string };
      mainCommit = data.sha?.slice(0, 12) ?? null;
    }
  } catch {
    /* optional */
  }

  const backendHealth = await probeBackendHealth(backendHttpUrl());

  return NextResponse.json({
    apiUrl: backendHttpUrl(),
    wsUrl: backendWsUrl(),
    mode: "proxy",
    bundleRevision: DASHBOARD_BUNDLE_REVISION,
    features: DASHBOARD_FEATURES,
    backendHealth,
    githubMainCommit: mainCommit,
    deployedGitSha: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 12) ?? null,
    promoteUrl:
      "https://vercel.com/apexweb-adams-projects/apex-trading-dashboard/deployments",
  });
}
