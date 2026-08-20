export function formatStorage(tb: number | undefined): string {
  const value = Number(tb ?? 0);
  if (value < 1) return `${Math.round(value * 1000)}GB`;
  return `${value.toFixed(1)}TB`;
}

// Issue #45 — native-currency price display, shared by watchlist/page.tsx
// (Best Price / Target Price / sheet-panel listing & target prices) and
// product-price-chart.tsx's tooltip. Deliberately NOT FX-converted here —
// that's a separate, explicit conversion (toCad(), step 5) applied only
// where the design calls for it (header total, sheet-panel secondary
// figure), so a price change here is never entangled with FX movement.
//
// `currency` is `Currency["USD" | "CAD" | "KRW"] | null` — typed loosely
// as `string | null` to avoid this shared lib file importing the API
// layer's type just for a signature; callers already have a real
// `Currency | null` and TypeScript accepts the narrower type at call
// sites.
export function fmtPrice(amount: number, currency: string | null): string {
  if (currency === "KRW") return `₩${Math.round(amount).toLocaleString("en-US")}`;
  if (currency === "USD") return `$${amount.toFixed(2)} USD`;
  // CAD or null (unresolved) — matches today's exact pre-#45 output.
  return `$${amount.toFixed(2)}`;
}

// Issue #45 — converts a native-currency amount to CAD using cached FX
// rates (rates: {"USD": 1.35, "KRW": 0.00098}, each "1 unit of that
// currency in CAD" — see backend's FxRatesResponse). CAD and null
// (unresolved currency) pass through unchanged — nothing to convert.
// Returns null (never NaN) when a conversion is actually needed but the
// rate isn't available yet — e.g. `rates` is `{}` before the first
// successful refresh_fx_rates run (bootstrap case, schema.md). Callers
// treat null as "exclude from sum" / "omit the CAD-equivalent suffix."
export function toCad(amount: number, currency: string | null, rates: Record<string, number>): number | null {
  if (currency === null || currency === "CAD") return amount;
  const rate = rates[currency];
  return rate === undefined ? null : amount * rate;
}

// Issue #45 — sheet-panel secondary figure, e.g. "$29 CAD" next to a
// native ₩30,000 price. null (not rendered) when there's nothing useful
// to show: already CAD/unresolved (toCad's passthrough case — a CAD
// figure showing "$X CAD" next to itself would be redundant, not
// informative), or the rate needed for a real conversion isn't cached yet.
export function fmtCadEquivalent(amount: number, currency: string | null, rates: Record<string, number>): string | null {
  if (currency === null || currency === "CAD") return null;
  const cad = toCad(amount, currency, rates);
  return cad === null ? null : `$${cad.toFixed(0)} CAD`;
}
