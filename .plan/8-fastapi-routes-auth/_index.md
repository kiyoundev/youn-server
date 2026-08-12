# Issue #8: FastAPI Routes + Auth

## PR / Branch
- **Branch:** `feature/8-fastapi-routes-auth`
- **PR Title:** `main | feature - 8 - FastAPI routes + auth`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ✅ Done | [review.md](review.md) |

## Success Criteria
<!-- From issue acceptance criteria + decisions made during api.md alignment review -->
- [x] All routes return 401 when `X-API-Key` header is missing or wrong
- [x] `GET /api/health` returns 200 with no auth header required
- [x] `POST /api/items` with known-domain URL (e.g. `amazon.ca`) sets `retailer` automatically, skips probe
- [x] `POST /api/items` with unknown-domain URL probes via extraction hierarchy, stores detected `scraper_type`
- [x] `POST /api/items` with explicit `scraper_type = "patchright"` in body stores that value, skipping auto-detection
- [x] `POST /api/items` with invalid `scraper_type` (not `null`/`"patchright"`) returns 422
- [x] `POST /api/items` with duplicate `url` (active or paused) returns 409
- [x] `POST /api/stocks` with invalid ticker returns 400
- [x] `POST /api/stocks` with duplicate `(ticker, direction)` (active or paused) returns 409
- [x] `POST /api/poll/prices` / `/api/poll/stocks` called twice within 5 minutes — second call returns 429 (independent windows)
- [x] `POST /api/poll/prices` / `/api/poll/stocks` cannot run concurrently with themselves or the scheduled job (in-memory lock)
- [x] `DELETE /api/items/{id}` cascades and removes all `PriceHistory` rows, returns 204 (verified against real DB)
- [x] `GET /api/items/{id}`, `GET /api/stocks/{id}`, and all `{id}` write routes return 404 for unknown IDs
- [x] `POST /api/stocks/{id}/analyze` creates a pending `AnalysisResult` and returns it; returns 409 if one is already running for that ticker
- [x] CORS allows requests from origin in `CORS_ORIGINS` env var
- [x] `PATCH`/`DELETE /api/stocks/{id}` keep `FinnhubClient`'s in-memory subscription cache in sync (add/remove/update)

## Estimated Effort
- Implementation: **7 hours**
- Testing: **2 hours**
- **Total: 9 hours**

(Original issue estimate was ~4h; scope expanded during `api.md` alignment review — see [context.md](context.md) for what changed and why.)
