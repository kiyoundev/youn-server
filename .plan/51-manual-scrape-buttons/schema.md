# Issue #51: Schema & API Contract

## API Routes

### `POST /api/poll/prices` (existing, unchanged)
- **Handler:** `backend/app/api/poll.py`
- **Request:** no body
- **Response:** `{"status": "queued"}` (200)
- **Error cases:** `429` — `{"detail": "Rate limited, try again in {N}s"}` if called within 5 minutes of the last trigger

### `POST /api/items/{product_id}/poll` (new)
- **Handler:** `backend/app/api/items.py`
- **Request:** no body; `product_id` path param
- **Response:** `{"status": "queued"}` (200)
- **Error cases:**
  - `404` — `{"detail": "Product not found"}` (reuses `_get_product_or_404`)
  - `429` — `{"detail": "Already scraping — try again shortly"}` if any of the product's listing ids are already in `in_flight_snapshot()`
  - `429` — `{"detail": "Rate limited, try again in {N}s"}` if triggered again within 45s of the last successful trigger for this product

## TypeScript Interfaces

```typescript
// frontend/src/lib/api/items.ts additions — no new types needed beyond the
// two new functions below; both return the same {status: "queued"} shape
// as the backend, but callers only care that the promise resolved.

export function pollAllPrices(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/proxy/poll/prices", { method: "POST" });
}

export function pollProduct(productId: number): Promise<{ status: string }> {
  return request<{ status: string }>(`${BASE}/${productId}/poll`, { method: "POST" });
}
```

## External API Contracts
None — both routes trigger existing internal scrape machinery only.
