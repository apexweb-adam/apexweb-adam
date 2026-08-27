import { NextRequest, NextResponse } from "next/server";
import { backendBase, fetchActiveGateStatus } from "@/lib/active-gate";

export const dynamic = "force-dynamic";

async function proxyRequest(req: NextRequest, pathSegments: string[]) {
  const path = pathSegments.join("/");
  const search = req.nextUrl.search;
  const target = `${backendBase()}/api/${path}${search}`;

  if (req.method === "GET" && path === "profitability" && !search) {
    try {
      const enriched = await fetchActiveGateStatus();
      return NextResponse.json(enriched);
    } catch {
      // fall through to plain proxy
    }
  }

  const init: RequestInit = {
    method: req.method,
    cache: "no-store",
    headers: {
      Accept: "application/json",
    },
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
    init.headers = {
      ...init.headers,
      "Content-Type": req.headers.get("content-type") || "application/json",
    };
  }

  const res = await fetch(target, init);
  const contentType = res.headers.get("content-type") || "application/json";
  const body = await res.text();

  return new NextResponse(body, {
    status: res.status,
    headers: { "Content-Type": contentType },
  });
}

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  const { path } = await ctx.params;
  return proxyRequest(req, path);
}

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  const { path } = await ctx.params;
  return proxyRequest(req, path);
}
