import { NextResponse } from "next/server";
import { DASHBOARD_BUNDLE_REVISION, DASHBOARD_FEATURES } from "@/lib/deploy-health";

export const dynamic = "force-dynamic";

function backendHttpUrl(): string {
  return (
    process.env.BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  ).replace(/\/$/, "");
}

function backendWsUrl(): string {
  const explicit =
    process.env.BACKEND_WS_URL || process.env.NEXT_PUBLIC_WS_URL || "";
  if (explicit) return explicit.replace(/\/$/, "");

  const http = backendHttpUrl();
  return http.replace(/^http:\/\//, "ws://").replace(/^https:\/\//, "wss://");
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
    promoteUrl:
      "https://vercel.com/apexweb-adams-projects/apex-trading-dashboard/deployments",
  });
}
