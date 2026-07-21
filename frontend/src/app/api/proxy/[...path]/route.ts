import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  const url = `${BACKEND_URL}/api/${path.join("/")}${request.nextUrl.search}`

  const resp = await fetch(url, {
    headers: { "X-API-Key": process.env.API_KEY ?? "" },
    cache: "no-store",
  })

  const body = await resp.text()
  return new NextResponse(body, {
    status: resp.status,
    headers: { "Content-Type": resp.headers.get("Content-Type") ?? "application/json" },
  })
}
