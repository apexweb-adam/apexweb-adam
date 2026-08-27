import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import {
  DASHBOARD_BUNDLE_REVISION,
  VERIFIED_PREVIEW_URL,
} from "@/lib/deploy-health";

/** Production aliases that may serve a stale bundle until promoted in Vercel. */
const STALE_PRODUCTION_HOSTS = [
  "apex-trading-dashboard-flame.vercel.app",
  "apex-trading-dashboard-apexweb-adams-projects.vercel.app",
];

export async function middleware(request: NextRequest) {
  const host = (request.headers.get("host") ?? "").split(":")[0].toLowerCase();
  if (!STALE_PRODUCTION_HOSTS.includes(host)) {
    return NextResponse.next();
  }

  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.next();
  }

  try {
    const configRes = await fetch(new URL("/api/config", request.url), {
      cache: "no-store",
    });
    if (configRes.ok) {
      const cfg = (await configRes.json()) as {
        bundleRevision?: string;
        features?: { activeGate?: boolean };
      };
      const bundleOk = cfg.bundleRevision === DASHBOARD_BUNDLE_REVISION;
      const gateOk = cfg.features?.activeGate === true;
      if (bundleOk && gateOk) {
        return NextResponse.next();
      }
    }
  } catch {
    /* fall through to verified preview */
  }

  const dest = new URL(
    request.nextUrl.pathname + request.nextUrl.search,
    VERIFIED_PREVIEW_URL
  );
  return NextResponse.redirect(dest, 307);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
