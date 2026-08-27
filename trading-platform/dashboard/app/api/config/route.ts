import { NextResponse } from "next/server";

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
  return NextResponse.json({
    apiUrl: backendHttpUrl(),
    wsUrl: backendWsUrl(),
    mode: "proxy",
  });
}
