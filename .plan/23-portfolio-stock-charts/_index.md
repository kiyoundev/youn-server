# #23: Portfolio Value & Stock Price History Charts

## PR / Branch
- **Branch:** `feature/23-portfolio-stock-charts`
- **PR Title:** `main | feature - 23 - Portfolio stock charts`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ⬜ Not started | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] `get_price_history()` accepts a `range` (`1D/1W/1M/3M/6M/YTD/ALL`) and an optional `native_currency`, returns correctly-shaped points for each
- [ ] `GET /api/market/{ticker}/history?range=...` returns those points; CAD-native tickers resolve through the same `.TO` rule live quotes use
- [ ] `/market/[ticker]`'s existing `MarketDetailChart` renders real data; range buttons switch the fetched series; no new chart component needed (superseded — see `challenges.md`)
- [ ] `GET /api/portfolio/history?range=...` returns `[{date, value}]` in CAD, derived via `compute_positions()` on a ledger-prefix per date point — no new position-reconstruction logic
- [ ] `/portfolio`'s overview chart plots the real series for all 7 ranges; no mock `chartDataByRange` remains
- [ ] The big Current Value total is identical across ranges; the change beside it is `(total − value at range start) / value at range start`
- [ ] A past point uses the shares held that date and that date's prices/FX rate; a stock bought later adds nothing before its first buy; a missing close carries the last known one, never zero
- [ ] A symbol with a genuine total fetch failure is logged and excluded from the affected points, never silently zeroed
- [ ] The dashed invested line on `/portfolio`'s chart uses `summary.invested_cad` (prop already exists on `PortfolioLineChart`, just unwired)
- [ ] Neither new route is polled on an interval — fetched only on page load / range change
- [ ] `DateRange` defined once (`lib/api/market.ts`), shared by both pages, replacing two independent definitions

## Estimated Effort
- Implementation: **6h** (backend: range mapping + 2 new routes + new orchestration service; frontend: type consolidation + wiring 2 pages)
- Testing: **2.5h**
- **Total: ~8.5h** (re-estimated from the issue doc's "~3h for the per-ticker chart; portfolio value history not yet estimated" — the stale-UI correction and the portfolio-history orchestration are both larger than the original text accounted for)
