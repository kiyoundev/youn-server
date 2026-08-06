import useSWR from "swr";

// Matches backend/app/schemas/price_history.py — GET /api/items/{pid}/listings/{lid}/history response shape.
export interface PriceHistoryPoint {
  id: number;
  watch_item_id: number; // NOT listing_id — matches the backend field name exactly
  price: number;
  checked_at: string;
}

const fetcher = (url: string) => fetch(url).then((r) => r.json());

// Exported separately so callers outside this hook (the SSE onmessage
// handler, which needs to mutate() this exact same SWR key on a push) never
// have to reconstruct the URL by hand and risk it drifting out of sync with
// the fetch below.
export function listingHistoryKey(productId: number, listingId: number): string {
  return `/api/proxy/items/${productId}/listings/${listingId}/history?days=30`;
}

// Backend route requires product_id in the path even though it only ever
// filters by listing_id internally — used solely for a 404 ownership check
// (items.py's _get_listing_or_404). Callers holding a full Listing object
// already have both IDs, so this isn't extra lookup work in practice.
export function useListingHistory(productId: number, listingId: number) {
  return useSWR<PriceHistoryPoint[]>(listingHistoryKey(productId, listingId), fetcher);
}

// Collapses one listing's raw history into one point per LOCAL calendar day
// (Date's local-aware getters, not UTC) — min price if a day had more than
// one check. Must run before merging multiple listings' histories together
// (challenges.md #3): two listings scraped seconds apart within the same
// cycle never share an exact checked_at, so merging first and bucketing
// after silently degrades "min across retailers" to "whichever listing
// happened to be scraped at that instant."
export function bucketByLocalDay(history: PriceHistoryPoint[]): { date: string; price: number }[] {
  const byDay = new Map<string, number[]>();
  for (const point of history) {
    const d = new Date(point.checked_at);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key)!.push(point.price);
  }
  return Array.from(byDay.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, prices]) => ({ date, price: Math.min(...prices) }));
}
