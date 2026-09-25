import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Distinct from the catch-all proxy ([...path]/route.ts): that one always
// re-encodes the outbound request with Content-Type: application/json,
// which would corrupt or drop this endpoint's multipart boundary. Next.js
// resolves this static path ahead of the catch-all's [...path] segment, so
// the JSON proxy stays untouched for every other route (issue #33).
//
// Body is buffered via arrayBuffer() rather than streamed through — same
// approach the catch-all already takes with request.text() — since a
// personal CSV export is small, and buffering avoids Node's fetch
// requiring `duplex: "half"` for a streaming request body.
export const dynamic = "force-dynamic";

// A real export is tens of KB. Both limits exist so a wrong file or a stuck
// backend fails fast instead of eating memory or spinning for minutes.
// MAX_UPLOAD_BYTES must match _MAX_UPLOAD_BYTES in backend/app/api/activities.py
// (checked here first so an oversized file is refused before it's buffered).
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
// A real import is milliseconds even against the NAS; this is generous.
const BACKEND_TIMEOUT_MS = 30_000;

export async function POST(request: NextRequest) {
  const apiKey = process.env.API_KEY;
  if (!apiKey) {
    console.error("Proxy misconfigured: API_KEY environment variable is not set");
    return NextResponse.json(
      { detail: "Proxy misconfigured: API_KEY environment variable is not set" },
      { status: 500 },
    );
  }

  // Forwarded verbatim — the multipart boundary string lives inside this
  // header's value (e.g. "multipart/form-data; boundary=----abc123"), not
  // just the body, so the backend can't parse the upload without it.
  const contentType = request.headers.get("Content-Type");

  // Browsers send Content-Length for a FormData upload, so an oversized file
  // can be refused without reading it. (The backend enforces the same cap on
  // its side for anything that arrives without the header.)
  if (Number(request.headers.get("Content-Length") ?? 0) > MAX_UPLOAD_BYTES) {
    return NextResponse.json(
      {
        detail: {
          code: "file_too_large",
          message: `File is larger than ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB — a Wealthsimple export is far smaller than that, so this probably isn't one`,
        },
      },
      { status: 413 },
    );
  }

  const body = await request.arrayBuffer();

  let resp: Response;
  try {
    resp = await fetch(`${BACKEND_URL}/api/activities/import`, {
      method: "POST",
      headers: {
        "X-API-Key": apiKey,
        ...(contentType ? { "Content-Type": contentType } : {}),
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
    });
  } catch (err) {
    // Backend down or hung — a clear message instead of a bare 500.
    const timedOut = err instanceof Error && err.name === "TimeoutError";
    console.error("Activity import proxy: backend request failed", err);
    return NextResponse.json(
      { detail: timedOut ? "The backend took too long to respond" : "Couldn't reach the backend" },
      { status: timedOut ? 504 : 502 },
    );
  }

  const responseBody = await resp.text();
  return new NextResponse(responseBody || null, {
    status: resp.status,
    headers: responseBody ? { "Content-Type": resp.headers.get("Content-Type") ?? "application/json" } : {},
  });
}
