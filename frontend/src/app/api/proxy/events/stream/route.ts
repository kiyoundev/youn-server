import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

// Distinct from the catch-all proxy ([...path]/route.ts): that one awaits a
// complete JSON response and re-serializes it. This one relays a long-lived
// SSE stream chunk-by-chunk — buffering it the same way would defeat the
// entire point (the browser would never see anything until the connection
// closed, which for SSE is "never").
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const resp = await fetch(`${BACKEND_URL}/api/events/stream`, {
    headers: { "X-API-Key": process.env.API_KEY ?? "" },
    cache: "no-store",
    // Propagates a browser disconnect to this outbound connection too —
    // without this, closing the tab would leave the proxy↔backend leg open
    // and leaking (see .plan/36-wishlist-page-real-data-sse/challenges.md #1).
    signal: request.signal,
  })

  return new NextResponse(resp.body, {
    status: resp.status,
    headers: {
      "Content-Type": resp.headers.get("Content-Type") ?? "text/event-stream",
      "Cache-Control": "no-cache",
    },
  })
}
