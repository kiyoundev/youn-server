# #23: Challenges & Notes

## Potential Challenges

1. **The issue card's described UI is stale.** It was written before `/market/[ticker]/page.tsx` existed, so it describes a new `StockHistoryChart` component with row-expand UI and `1M/1Y/3Y/ALL` presets that don't match current reality — the real page, the real `MarketDetailChart`, and the real row-click-navigates (not expand) pattern already exist. Mitigation: this plan builds against the actual current frontend, not the issue text's original description; `context.md` documents the divergence explicitly so a future reader isn't confused by the gap between the two.

2. **yfinance call volume for the portfolio chart.** Unlike the per-ticker page (one symbol, one call), `/api/portfolio/history` needs one `get_price_history` call per *distinct symbol ever held in the range* — for a portfolio with many holdings, that's several concurrent yfinance calls per request. Mitigation: calls run concurrently (`asyncio.gather`), and per the grill-me decision, this route is **not** polled every 30s — only fetched on page load or range change — so the cost is bounded and infrequent, not a steady-state load. If visit volume ever grows enough to matter, a `fx_rate_history`-style persistent cache (deliberately not built now) is the natural next step.

3. **A symbol with no price data anywhere in its fetched range** (not a weekend/holiday gap, which carry-forward already handles — a genuine total failure, e.g. delisted ticker, yfinance outage for that symbol specifically). Mitigation: logged and excluded from the affected date points' sum rather than counted as a silent 0 — matches this codebase's established "never fabricate, degrade and log" convention (`fx.py`, `prices.py`). Documented as an accepted edge case, not solved with new retry/fallback machinery — it should be rare once a symbol has ever resolved once.

4. **CAD-native ticker resolution without a currency hint.** `/market/{ticker}` navigates using the raw ledger symbol alone (e.g. `"RY"`), which collides with real tickers on other exchanges if queried bare. Mitigation: the route takes an optional `native_currency` query param (frontend passes it whenever the ticker is a known held position); a browsed-but-unheld ticker (e.g. Popular Assets) has no currency context and queries the bare ticker, same as today's all-USD mock tickers — not a regression, just not yet correct for a hypothetical browsed CAD-native ticker outside the portfolio (out of scope; no such UI entry point exists today).

## Key Differences

| Aspect | Current (issue text / existing code) | Target |
|---|---|---|
| Per-ticker chart UI | Issue text: new `StockHistoryChart`, row-expand, `1M/1Y/3Y/ALL` | Reuse existing `/market/[ticker]` page + `MarketDetailChart`, real data only |
| Range vocabulary | `/market/[ticker]`: 8 values (`...1Y/10Y`); `/portfolio`: 7 values (`...ALL`), defined twice | One shared 7-value `DateRange` (`1D/1W/1M/3M/6M/YTD/ALL`), defined once |
| `get_price_history` | `(ticker, period)`, daily-only, zero callers | `(ticker, range_, native_currency=None)`, range-aware, used by 2 routes |
| Position-as-of-a-past-date | Doesn't exist | `compute_positions()` called on a ledger-prefix, no new reconstruction logic |
| Historical price caching | None (get_price_history uncached, unused) | Still none, deliberately — see Potential Challenges #2 |
| `/api/portfolio/history`, `/api/market/{ticker}/history` polling | N/A (routes don't exist) | No `refreshInterval` — fetch only on load/range-change, unlike `/api/positions`'/`/api/portfolio/summary`'s 30s poll |

## Rollback Plan
1. Revert the branch — both new routes are additive (no migration, no schema change to anything existing), and `get_price_history`'s signature change has no production callers to break.
2. Frontend reverts cleanly to the mock `chartDataByRange`/`generateMockPriceSeries` state, since this plan removes rather than reshapes them — `git revert` leaves no orphaned real-data plumbing behind.
