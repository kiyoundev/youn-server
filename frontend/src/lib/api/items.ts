// Thin data layer between watchlist/page.tsx's mutation handlers and
// fetch() — one named function per write path instead of six near-duplicate
// inline fetch() calls, and one shared place (request()) that turns a
// non-2xx response into a typed, catchable error instead of silently
// resolving (fetch() itself never rejects on 4xx/5xx).
//
// Always goes through /api/proxy/items — never the backend directly — same
// reason the proxy exists at all (see route.ts): the backend's X-API-Key
// must never reach the browser.

// Matches backend/app/schemas — GET /api/items response shape. Mirrors
// watchlist/page.tsx's local Product/Listing interfaces.
export type WatchStatus = "watching" | "triggered" | "paused" | "failed" | "processing" | "out_of_stock";

// Issue #45 — mirrors backend's Currency = Literal["USD","CAD","KRW"]
// (schemas/product.py). Product-level, not per-Listing — a single product
// never mixes currencies across its retailer listings (see
// .plan/45-multi-currency-support/context.md).
export type Currency = "USD" | "CAD" | "KRW";

export interface Listing {
  id: number;
  retailer: string;
  url: string;
  last_price: number | null;
  last_scrape_status: "ok" | "oos" | "error" | null;
  restock_at: string | null;
  // Issue #53 — why the last scrape failed. Null while healthy, and for a
  // listing that was already "error" before this field existed until its
  // next scrape.
  last_scrape_error: string | null;
  // When this listing was last polled, whatever the outcome.
  last_checked: string | null;
  product_id: number;
  created_at: string;
}

export interface Product {
  id: number;
  // Nullable (issue #44) — blank until process_item infers it from the
  // first successful scrape's product_title, if the user left it blank.
  name: string | null;
  target_price: number;
  // Nullable (issue #45) — NULL until process_item infers it from the
  // first successful scrape, unless the user's already set it manually
  // (manual override always wins over re-detection).
  currency: Currency | null;
  alerted_at: string | null;
  status: WatchStatus;
  last_checked: string | null;
  listings: Listing[];
  created_at: string;
}

// Request payloads — mirror the backend's ProductCreate/ProductUpdate/
// ListingCreate/ListingUpdate schemas (schema.md).
export interface ProductCreatePayload {
  // Optional (issue #44) — omitted or blank, Product.name stays NULL until
  // inferred from the first successful scrape.
  name?: string;
  target_price: number;
  // Issue #63 — explicit override; omitted lets the first scrape infer it
  // (same "manual always wins" rule as ProductUpdatePayload.currency).
  currency?: Currency;
  // Zero or more listing URLs, created in the same request (bulk, not
  // chained) — backend probes retailer/scraper_type for each concurrently
  // (bounded). A duplicate or unscrapable URL doesn't fail the whole
  // request — it shows up in the response's `failed` list instead.
  urls: string[];
}

export interface ListingCreatePayload {
  url: string;
}

export interface ProductUpdatePayload {
  name?: string;
  target_price?: number;
  // Pause/resume for the whole product — cascades to every listing (none
  // are scraped while false), not settable per listing (see
  // ListingUpdatePayload).
  active?: boolean;
  // Issue #45 — present-and-non-null always overwrites; manual override
  // always wins over prior/future auto-detection from a scrape.
  currency?: Currency;
}

export interface ListingUpdatePayload {
  url?: string;
}

// Matches backend's ListingFailure/ProductCreateResponse — POST /api/items's
// actual response shape, not just Product, since a partial add (some URLs
// succeeded, some didn't) needs to be representable in one response.
export interface ListingFailure {
  url: string;
  detail: string;
  // Hostname-derived (issue #44) — same fallback a real listing gets at
  // creation, not real inference (a failed-to-scrape URL has no successful
  // scrape to infer a display name from).
  retailer: string;
}

export interface ProductCreateResult {
  product: Product;
  failed: ListingFailure[];
}

// Matches backend's FxRatesResponse (schemas/fx.py). rates: e.g.
// {"USD": 1.35, "KRW": 0.00098} — CAD is implicit 1.0, never a key here.
// Read-only, served from a table refreshed daily server-side — this call
// never touches the upstream FX source directly.
export interface FxRates {
  rates: Record<string, number>;
  stale: boolean;
  fetched_at: string | null;
}

// Thrown on any non-2xx response so callers can branch on status (e.g. 409
// -> "already watched" toast vs. a generic failure toast) instead of every
// call site re-parsing the response body by hand.
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

const BASE = "/api/proxy/items";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.detail ?? `Request failed with status ${res.status}`);
  }

  // DELETE routes return 204 with no body — nothing to parse.
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function createProduct(payload: ProductCreatePayload): Promise<ProductCreateResult> {
  return request<ProductCreateResult>(BASE, { method: "POST", body: JSON.stringify(payload) });
}

export function createListing(productId: number, payload: ListingCreatePayload): Promise<Listing> {
  return request<Listing>(`${BASE}/${productId}/listings`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateProduct(productId: number, payload: ProductUpdatePayload): Promise<Product> {
  return request<Product>(`${BASE}/${productId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function updateListing(productId: number, listingId: number, payload: ListingUpdatePayload): Promise<Listing> {
  return request<Listing>(`${BASE}/${productId}/listings/${listingId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteProduct(productId: number): Promise<void> {
  return request<void>(`${BASE}/${productId}`, { method: "DELETE" });
}

export function deleteListing(productId: number, listingId: number): Promise<void> {
  return request<void>(`${BASE}/${productId}/listings/${listingId}`, { method: "DELETE" });
}

// Issue #51 — manual rescrape, outside the normal 6h schedule. Both return
// {"status": "queued"} immediately; results land via the existing SSE flow
// (subscribeToListingEvents -> mutate("/api/proxy/items")), same as every
// other mutation on this page — no new polling loop needed here either.

// Whole-watchlist rescrape. Not under BASE ("/api/proxy/items") — relays to
// the backend's existing POST /api/poll/prices (from #6), rate-limited
// there to one call per 5 minutes, process-wide.
export function pollAllPrices(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/proxy/poll/prices", { method: "POST" });
}

// Single-product rescrape — only this product's own listings, not the
// whole watchlist. Rate-limited per-product server-side (45s cooldown, plus
// an in-flight guard) — see backend/app/api/items.py:poll_item.
export function pollProduct(productId: number): Promise<{ status: string }> {
  return request<{ status: string }>(`${BASE}/${productId}/poll`, { method: "POST" });
}

// Not under BASE ("/api/proxy/items") — the proxy is a generic [...path]
// catch-all (route.ts), so "/api/proxy/fx-rates" relays straight to the
// backend's GET /api/fx-rates with no new proxy code needed.
export function getFxRates(): Promise<FxRates> {
  return request<FxRates>("/api/proxy/fx-rates");
}
