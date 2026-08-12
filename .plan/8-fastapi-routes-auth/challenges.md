# Issue #8: Challenges & Notes

## Potential Challenges

1. **Migration may fail on existing duplicate data** — the new `UNIQUE(url)` and `UNIQUE(ticker, direction)` constraints will fail to apply if the dev DB already contains duplicate rows (e.g. from earlier manual testing). Mitigation: query for duplicates before generating the migration; dedupe manually if found.

2. **POST `/api/items` latency on probe path** — when a domain isn't in `RETAILER_MAP` and no `scraper_type` override is given, the create request synchronously runs `HTTPScraper` and potentially `PatchrightScraper` before responding. Patchright alone can take 5-15s. **Confirmed:** accept the wait — request blocks until the probe finishes and the result is written to DB. No async/background alternative needed.

3. ~~**`FinnhubClient._check_threshold()` and `_cache` are "private"...**~~ **Resolved:** add two small public methods to `FinnhubClient` — `cached_tickers() -> list[str]` and `check_threshold(ticker, price) -> None` (thin wrapper around `_check_threshold`). `poll_stocks()` calls these instead of reaching into `_cache`/`_check_threshold` directly. See [implementation.md](implementation.md) step 5.

4. **Patchright resource pressure on Pi 5** — if a manual `/api/poll/prices` trigger overlaps with the scheduled 6h job (prevented by the new lock) or if multiple Patchright-requiring items exist, sequential scraping (not parallel) is the only thing keeping memory bounded. The lock prevents *concurrent poll cycles*, but a single cycle with many Patchright items is still slow — not addressed by this issue, just noting it's not a regression either.

5. ~~**`POST /api/stocks/{id}/analyze` price source can fail**~~ **Resolved:** this route is a debug/manual-trigger tool only — the real usage path is automatic (threshold crossing + `run_analysis=true`). No live Finnhub fetch at all; uses `alert.last_price` directly as `triggered_price`, which required making `AnalysisResult.triggered_price` nullable (it can be `null` for an alert that's never fired). Simpler than the live-fetch design, and matches the route's actual purpose.

6. **Rate-limit state is in-memory, per-process** — both `/api/poll/prices` and `/api/poll/stocks` rate-limit timestamps reset on server restart. This is consistent with the issue's original design ("in-memory timestamp") and acceptable for a single-instance Pi deployment, but worth remembering if the app is ever made multi-process.

## Key Differences From Original Issue Text

| Aspect | Original Issue (`.doc/issues.md`) | Final Plan |
|--------|-----------------------------------|------------|
| Stocks router scope | GET/POST/PATCH/DELETE only | + `POST /analyze`, `GET /analysis` |
| Items/stocks reads | List only | + singular `GET /{id}` |
| Poll response | Unspecified | `{"status": "queued"}`, not `{"triggered": true, "items_checked": int}` from `api.md` |
| Poll concurrency | Not mentioned | New `asyncio.Lock` guard, shared with scheduled job |
| `poll_stocks()` job | Didn't exist | New — REST fallback reusing Finnhub WS threshold logic |
| Duplicate prevention | Not mentioned | `UNIQUE(url)`, `UNIQUE(ticker, direction)` + 409 |
| Auth missing-header behavior | Issue says 401; `api.md`'s code snippet would've produced 422 | Fixed to 401 via `Header(None)` |

## Rollback Plan
1. Revert the feature branch; `app/main.py`'s original inline routes are simple enough to restore from git history if needed.
2. If the unique-constraint migration causes problems in a deployed DB (unexpected existing duplicates), roll back via `alembic downgrade -1` before reverting code.
3. Verify `GET /api/health` still responds 200 post-rollback (smoke test for the whole API surface).
