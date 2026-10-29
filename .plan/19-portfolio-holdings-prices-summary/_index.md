# #19: Portfolio Holdings — Derived Positions, Prices & Summary

## PR / Branch
- **Branch:** `feature/19-portfolio-holdings-prices-summary` (nominal — solo project commits straight to `main`)
- **PR Title:** `main | feature - 19 - Portfolio holdings, prices & summary`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | 🔄 Code done; step 7 (user validation) open | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Decisions (from grill, defaults accepted)
| # | Question | Decision |
|---|----------|----------|
| 1 | Same symbol across accounts | Merge into one row per `(symbol, native_currency)` — shares summed, avg cost share-weighted |
| 2 | Mock-only `assetType` / `purchasedAt` | ~~Dropped~~ Reversed 2026-10-28: both come back, derived from real data. See decisions 12 and 13 |
| 3 | "No mock data remains" scope | Holdings list + summary figures only. Chart, donut, growth rate, Watchlist tile (#10.6), Popular Assets (#30) stay mock |
| 4 | Last-known price persistence | In-memory only; lost on restart |
| 5 | Empty ledger | Empty state pointing to the activities import upload |
| 6 | Cash currency | CAD — verified: `wealthsimple_csv.py` rejects any non-CAD activity currency |
| 7 | Finnhub key shared Mac/Pi | Assume shared; REST 60/min budget is shared — risk in challenges.md |
| 8 | CAD price source | yfinance (verified live: Finnhub free key returns HTTP 403 for `AVGO.TO`, `SHOP.TO`, `XIU.TO`; yfinance returns `AVGO.TO` 13.08 CAD) |
| 9 | Positions recomputed per poll? | No — merged holdings + cash cached in memory, cleared after commit by the import and reset routes (single uvicorn process assumed). Only quotes are refetched |
| 10 | Balance FX | `balance_cad` = CAD value + USD value × **today's** `fx_rates` USD row + cash (decided 2026-10-26). Trade-time rates only feed cost (`avg_cost_cad`); no CAD cost basis or CAD gain is shown — gains stay per native currency. No USD holdings (or none priced) → rate not needed, `fx_available: true`. USD holdings and no USD row → `balance_cad: null`, `fx_available: false`. Row older than 24h → still converted, `fx_stale: true` |
| 11 | Ledger warnings on `/positions` | Dropped (2026-10-26). The only warning (history doesn't start with a deposit) is already shown at import (#33); no later issue extends the response, so `GET /api/positions` returns a bare `PositionResponse[]` and `LedgerSnapshot` has no `warnings` |
| 12 | Asset type badge (replaces `assetType`) | `asset_type: "Stock" \| "ETF" \| "CDR" \| null` (decided 2026-10-28). From yfinance `quote_type`: EQUITY → Stock, ETF → ETF. A CAD-native ETF whose `.info` `shortName` contains "CDR" → CDR, because Yahoo files CDRs as ETF (checked on 0.2.59 and 1.7.0). Anything else, or a failed lookup → `null`, no badge. New `AssetTypeService`, separate from `PriceService`: a success is cached for the process, a failure is retried after 5 min, 5 s limit per lookup. Only `/api/positions` uses it; the yfinance pin does not change |
| 13 | Date column (replaces `purchasedAt`) | `last_traded_at`: the latest `Trade` row per `(account, symbol)`, the latest across accounts once merged (decided 2026-10-28). Kept after a full sell. The importer allows only `Trade/BUY` today, so in practice it is the last purchase. The tile reads "Last traded Mon YYYY" |
| 14 | Summary trio (revised) | **Companies** = holdings count, **Balance** = `cash_cad` (the cash left over), **Committed** = `invested_cad` (CAD paid for the held shares at purchase-time rates; new summary field, decided 2026-10-29). Per-currency subtotals, the "excludes N unpriced" and stale-rate notes, and `balance_cad` on the page are dropped: nothing shown depends on prices or FX. Replaces decision 10's use of `balance_cad` as the trio's Balance; `balance_cad` stays in the API |
| 15 | Overview total | The big "Current Value" is the real `balance_cad`, identical for every range; the chart and any per-range change stay mock/absent until #23 (extended 2026-10-29 to portfolio value history; the USD→CAD history is #74). The chart no longer takes the mock invested line |
| 16 | Allocation | Backend `allocation` per row: value in CAD over the priced holdings' CAD total, USD at today's `fx_rates` rate (Wealthsimple's own page implies a current rate, ~1.399 vs ours 1.4047); `null` when unpriced or no rate; rows sorted by it. UI column postponed |
| 17 | Logos | Wealthsimple's host instead of Finnhub's (2026-10-29): `{ticker}-{exchange}.png`, exchange tried in order from native currency, white box with the ticker on failure. Per-share price and avg cost are not shown on the row |

## Success Criteria
- [x] `GET /api/positions` returns holdings derived from `activities` via `compute_positions()`; no manual create/update/delete routes
- [x] Holdings never call `subscribe()` / `unsubscribe()` — WS subscriptions stay `StockAlert`-driven
- [x] USD-native prices from Finnhub REST; CAD-native from yfinance with `.TO` rule + override map
- [x] yfinance currency ≠ holding native currency → no price, flagged `currency_mismatch`
- [x] One shared server-side TTL cache (~15s); on upstream error the last known price is served and marked `stale`
- [x] Holdings + cash cached in memory; import and reset clear it after commit; a second poll reads no `activities` rows; a failed import / ledger error never poisons it
- [x] Gains shown in each holding's native currency (USD cost basis from #33)
- [x] `GET /api/positions` rows carry `last_traded_at` and `asset_type` (`Stock` / `ETF` / `CDR` / `null`); a failed or slow type lookup never changes a row's price or `price_status`
- [x] `GET /api/portfolio/summary` returns per-currency invested / market value / unrealized gain, CAD cash, CAD account balance, `invested_cad`
- [x] `GET /api/positions` rows carry `allocation` and are ordered by CAD value
- [ ] `/portfolio` Holdings tile and summary figures read real data via 30s SWR poll; no SSE; empty-ledger state shown
- [x] Backend tests green; `tsc` and `eslint` clean

## Estimated Effort
- Implementation: **3 hours**
- Testing: **1 hour**
- **Total: 4 hours** (matches issue estimate)
