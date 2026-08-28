import { NextResponse } from "next/server";
import { DASHBOARD_BUNDLE_REVISION, DASHBOARD_FEATURES } from "@/lib/deploy-health";
import { resolveBackendHttpUrl, resolveBackendWsUrl } from "@/lib/production-backend";

export const dynamic = "force-dynamic";

function backendHttpUrl(): string {
  return resolveBackendHttpUrl();
}

function backendWsUrl(): string {
  return resolveBackendWsUrl(backendHttpUrl());
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

  return NextResponse.json({
    apiUrl: backendHttpUrl(),
    wsUrl: backendWsUrl(),
    mode: "proxy",
    bundleRevision: DASHBOARD_BUNDLE_REVISION,
    features: DASHBOARD_FEATURES,
    githubMainCommit: mainCommit,
    deployedGitSha: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 12) ?? null,
    promoteUrl:
      "https://vercel.com/apexweb-adams-projects/apex-trading-dashboard/deployments",
  });
}
