import { toCad } from "@/lib/format";
import type { Product, WatchStatus } from "@/lib/api/items";

// Issue #56 — watchlist table sorting. Pure, so it can be unit-tested once
// the frontend test suite (#29) exists.

export type SortKey = "name" | "retailer" | "best_price" | "target_price" | "status" | "last_checked";
export type SortDir = "asc" | "desc";
export interface SortState {
  key: SortKey;
  dir: SortDir;
}

// The cheapest price you can actually buy at — out-of-stock listings are left
// out (issue #68): they keep the retailer's last listed price for display, but
// a sold-out offer must not read as the product's best price. null when no
// listing is both in stock and priced (e.g. every retailer OOS) — callers
// render a "—" fallback rather than treating this as 0.
export const bestPrice = (product: Product): number | null => {
  const prices = product.listings
    .filter((l) => l.last_scrape_status !== "oos")
    .map((l) => l.last_price)
    .filter((p): p is number => p !== null);
  return prices.length > 0 ? Math.min(...prices) : null;
};

// A status is a word, not a number, so the Status column needs an explicit
// order. Lower rank sorts first in ascending: the rows you can act on
// (a hit target, then a broken scrape, then out of stock) come first, and
// the passive ones (processing, watching, paused) last. This is deliberately
// *not* compute_status()'s priority order (product_status.py), which exists
// to decide which status a product shows — it puts "paused" first.
// Record<WatchStatus, number> makes adding a status without ranking it here
// a compile error.
const STATUS_RANK: Record<WatchStatus, number> = {
  triggered: 0,
  failed: 1,
  out_of_stock: 2,
  processing: 3,
  watching: 4,
  paused: 5,
};

type SortValue = string | number | null;

// Value to compare for each column. null means "no sortable value" and
// sorts last in both directions (see sortProducts).
function sortValue(product: Product, key: SortKey, fxRates: Record<string, number>): SortValue {
  switch (key) {
    case "name":
      return (product.name ?? "Untitled").toLowerCase();
    case "retailer": {
      const labels = product.listings.map((l) => l.retailer.toLowerCase());
      return labels.length > 0 ? labels.sort((a, b) => a.localeCompare(b))[0] : null;
    }
    // Compared in CAD (not native currency) — a product list can mix KRW,
    // USD and CAD, and a raw ₩30,000 would otherwise sort above $500. null
    // when there's no price, or no FX rate cached yet for the currency.
    case "best_price": {
      const best = bestPrice(product);
      return best === null ? null : toCad(best, product.currency, fxRates);
    }
    case "target_price":
      return toCad(product.target_price, product.currency, fxRates);
    case "status":
      return STATUS_RANK[product.status];
    case "last_checked":
      return product.last_checked === null ? null : new Date(product.last_checked).getTime();
  }
}

const byCreatedThenId = (a: Product, b: Product): number =>
  new Date(a.created_at).getTime() - new Date(b.created_at).getTime() || a.id - b.id;

// Returns a new array. With no sort, the original oldest-first order. Ties
// fall back to that same order, so equal rows never reshuffle on re-render
// or an SSE update.
export function sortProducts(
  products: Product[],
  sort: SortState | null,
  fxRates: Record<string, number>,
): Product[] {
  if (sort === null) return [...products].sort(byCreatedThenId);

  const sign = sort.dir === "asc" ? 1 : -1;
  return [...products].sort((a, b) => {
    const va = sortValue(a, sort.key, fxRates);
    const vb = sortValue(b, sort.key, fxRates);
    // Missing values last in both directions — checked before `sign` is
    // applied so descending doesn't flip them to the top.
    if (va === null && vb === null) return byCreatedThenId(a, b);
    if (va === null) return 1;
    if (vb === null) return -1;
    const cmp = typeof va === "string" ? va.localeCompare(vb as string) : va - (vb as number);
    return cmp * sign || byCreatedThenId(a, b);
  });
}

// asc -> desc -> cleared (back to the default order); a different column
// starts at asc.
export function nextSort(current: SortState | null, key: SortKey): SortState | null {
  if (current === null || current.key !== key) return { key, dir: "asc" };
  return current.dir === "asc" ? { key, dir: "desc" } : null;
}
