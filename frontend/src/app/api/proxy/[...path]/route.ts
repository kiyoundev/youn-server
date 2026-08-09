import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Next.js 14 GET route handlers default to cacheable unless told otherwise —
// the internal fetch's `cache: "no-store"` below isn't reliably sufficient
// on its own across 14.x to keep the route itself out of the Full Route
// Cache. Without this, the first-ever request could get frozen and served
// forever after, regardless of what the backend actually returns later.
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path: string[] }> };

async function relay(request: NextRequest, path: string[], method: string) {
  const apiKey = process.env.API_KEY;
  if (!apiKey) {
    // Fail loud here rather than sending an empty X-API-Key: the backend
    // would still reject that with its own 401 "Invalid API key"
    // (core/auth.py), indistinguishable from a real bad-credential case.
    // This tells you specifically that the Next.js server's own env is
    // misconfigured, not that the backend rejected an actual auth attempt.
    console.error("Proxy misconfigured: API_KEY environment variable is not set");
    return NextResponse.json(
      { detail: "Proxy misconfigured: API_KEY environment variable is not set" },
      { status: 500 },
    );
  }

  const url = `${BACKEND_URL}/api/${path.join("/")}${request.nextUrl.search}`;
  const hasBody = method !== "GET" && method !== "DELETE";
  const resp = await fetch(url, {
    method,
    headers: {
      "X-API-Key": apiKey,
      ...(hasBody ? { "Content-Type": "application/json" } : {}),
    },
    body: hasBody ? await request.text() : undefined,
    cache: "no-store",
  });
  const body = await resp.text();
  return new NextResponse(body || null, {
    status: resp.status,
    headers: body ? { "Content-Type": resp.headers.get("Content-Type") ?? "application/json" } : {},
  });
}

export async function GET(req: NextRequest, ctx: RouteContext) {
  return relay(req, (await ctx.params).path, "GET");
}
export async function POST(req: NextRequest, ctx: RouteContext) {
  return relay(req, (await ctx.params).path, "POST");
}
export async function PATCH(req: NextRequest, ctx: RouteContext) {
  return relay(req, (await ctx.params).path, "PATCH");
}
export async function DELETE(req: NextRequest, ctx: RouteContext) {
  return relay(req, (await ctx.params).path, "DELETE");
}
