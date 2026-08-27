import { NextRequest, NextResponse } from "next/server";
import type { Portfolio, ProfitabilityStatus, StrategyConfig, Trade } from "@/lib/api";
import { enrichProfitabilityStatus } from "@/lib/profitability";

export const dynamic = "force-dynamic";

function backendBase(): string {
  return (
    process.env.BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  ).replace(/\/$/, "");
}

async function fetchBackendJson<T>(path: string): Promise<T> {
  const res = await fetch(`${backendBase()}/api/${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`backend ${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

/** Enrich gate at the proxy when Render has not deployed paused-bot logic yet. */
async function profitabilityWithActiveBots(): Promise<ProfitabilityStatus> {
  const [profitability, strategies, portfolios, trades] = await Promise.all([
    fetchBackendJson<ProfitabilityStatus>("profitability"),
    fetchBackendJson<StrategyConfig[]>("strategies"),
    fetchBackendJson<Portfolio[]>("portfolios"),
    fetchBackendJson<Trade[]>("trades?limit=200"),
  ]);
  return enrichProfitabilityStatus(profitability, trades, portfolios, strategies) ?? profitability;
}

async function proxyRequest(req: NextRequest, pathSegments: string[]) {
  const path = pathSegments.join("/");
  const search = req.nextUrl.search;
  const target = `${backendBase()}/api/${path}${search}`;

  if (req.method === "GET" && path === "profitability" && !search) {
    try {
      const enriched = await profitabilityWithActiveBots();
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
