import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function backendBase(): string {
  return (
    process.env.BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  ).replace(/\/$/, "");
}

async function proxyRequest(req: NextRequest, pathSegments: string[]) {
  const path = pathSegments.join("/");
  const search = req.nextUrl.search;
  const target = `${backendBase()}/api/${path}${search}`;

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
