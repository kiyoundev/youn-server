// Issue #62 — scraper noise tolerance, shared by the watchlist table's
// sparkline and the sheet's price chart so the two can't drift apart.
// Different scrape paths for the same retailer can record slightly
// different decimal precision for what's really the same listed price
// (e.g. $799.99 vs $799.00), so a series that stays within this range is
// treated as unchanged and drawn flat. Native-currency units, so this is
// effectively USD/CAD-only in practice (KRW amounts are large enough that
// 1 ~= exact equality, no regression).
export const PRICE_NOISE_THRESHOLD = 1;

export function isWithinNoise(prices: number[]): boolean {
  if (prices.length < 2) return true;
  return Math.max(...prices) - Math.min(...prices) <= PRICE_NOISE_THRESHOLD;
}

// The value to plot for every point of a series that's within noise: the
// latest price, so the flat line sits at where the price is now. Null when
// the series moved more than the threshold and should be drawn as-is.
export function flatPlotPrice(prices: number[]): number | null {
  return prices.length > 0 && isWithinNoise(prices) ? prices[prices.length - 1] : null;
}
