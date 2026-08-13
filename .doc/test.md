# Tests

## Test Framework & Tooling

**Backend** — `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`, `pyproject.toml`) + `respx` (mocks `httpx` calls at the transport level — used for any test hitting an external HTTP API, e.g. Pushover, DSM) + `unittest.mock` (`AsyncMock`/`MagicMock`/`patch` for mocking internal collaborators like `FinnhubClient` or `SynologyClient`). Tests live in `backend/tests/`, mirroring `app/`'s structure (`tests/api/`, `tests/services/`, `tests/scraper/`, `tests/scheduler/`, `tests/consumers/`, `tests/schemas/`, `tests/scripts/`, plus a few top-level files). Run via `pytest` from `backend/`.

**Frontend** — none yet. No test framework configured in `frontend/package.json`. Proposed: **Vitest** — fast, native ESM/TS support, no browser environment needed to unit-test a Next.js route handler (it's just an async function). Not yet set up; tracked below.

Existing backend test files, for reference:

| File | Covers |
|---|---|
| `tests/test_auth_and_cors.py` | `verify_api_key` dependency, CORS config |
| `tests/test_lifespan.py` | `main.py`'s `lifespan()` startup/shutdown sequence |
| `tests/test_notify.py` | `services/notifications.py` (Pushover via `respx`) |
| `tests/test_stocks.py` | `services/stocks.py` (`FinnhubClient`) |
| `tests/api/test_items_routes.py` | `GET/POST/PATCH/DELETE /api/items` |
| `tests/api/test_poll_routes.py` | `POST /api/poll/prices`, `/api/poll/stocks` |
| `tests/api/test_stocks_routes.py` | `/api/stockalerts/*` alert routes |
| `tests/api/test_analysis_routes.py` | `/api/analysis/tradingagents/*` |
| `tests/services/test_trading_agents.py` | `services/trading_agents.py` subprocess/heartbeat logic |
| `tests/scraper/*`, `tests/scheduler/*`, `tests/consumers/*`, `tests/schemas/*` | scraper routing, scheduled jobs, event dispatcher, Pydantic schema validation |

No existing coverage for `app/services/synology.py` or `app/api/system.py` — gap this doc's API section tracks below.

### Shared fixtures — `tests/conftest.py`

pytest auto-discovers any file named `conftest.py` and makes its fixtures available to every test file in that directory and below, with no import needed — this repo had none until the Synology test work below needed one. Lives at the top level (`tests/conftest.py`, not nested under `tests/api/` or `tests/services/`) because its one fixture is consumed by files in both of those directories, and a nested conftest wouldn't reach across sibling directories.

**Currently defined:**

| Fixture | Returns | Used by |
|---|---|---|
| `sample_storage_state` | A `StorageState` (2 bays — one healthy, one empty — `available=5.0`, `used=3.0`, `reserved=0.5`) | `tests/api/test_system_routes.py` (canned return value patched onto `SynologyClient.get_storage`) |

**Deliberately not added yet** — real, evidence-backed candidates (found via a grep audit of the existing suite), deferred as a separate cleanup task rather than folded into the Synology work:

| Candidate | Would replace | Seen in |
|---|---|---|
| `mock_db` | `db = MagicMock(); db.add = MagicMock(); db.commit = AsyncMock()` | `test_items_routes.py`, `test_stocks_routes.py`, `test_auth_and_cors.py`, `scheduler/test_jobs.py`, `consumers/test_dispatcher.py` — most-duplicated pattern in the suite |
| `make_request` (factory) | `test_stocks_routes.py`'s local `_request_with_finnhub` — fake `Request` wrapping `app.state.X` | `test_stocks_routes.py`, `test_poll_routes.py`, similar shape in `test_lifespan.py` |
| `mock_process` | Hand-rolled subprocess mock (`communicate`/`kill`/`stdout`/`stderr`) | `test_analysis_routes.py`, `services/test_trading_agents.py` |

Adopting these means retrofitting several already-passing test files to use the shared fixture instead of their inline mocks — a real but separate refactor, not something to do as a side effect of unrelated feature work.

**Deliberately never shared** — `monkeypatch.setattr(settings, ...)` blocks and `respx.mock` routes stay local per file; each patches/mocks a disjoint, domain-specific set of values (Finnhub token vs. Pushover creds vs. DSM host), so there's no common shape worth extracting.

---

## Sections

- **API** (this doc's current focus — below)
- **Frontend** — not yet started
- **E2E / integration** — not yet started

---

## API

### Synology Storage — `SynologyClient` (`app/services/synology.py`)

**✅ Implemented** — `tests/services/test_synology.py`, 8 tests, all passing. Recently rewritten (see `keynotes.md`'s "Concurrent Session Invalidation" entry) to fix a session-race bug — the caching/lock/retry logic below is exactly the kind of thing worth locking down with tests, and doing so surfaced no bugs in the new code.

**Scenarios covered** (`respx`-mocked DSM endpoints):

| Scenario | Asserts |
|---|---|
| First call, no cached sid | Triggers one login call, one fetch call |
| Second call, sid already cached | No login call — fetch reuses cached sid |
| Fetch fails with DSM code 119 or 106 | Exactly one relogin, one retried fetch, returns the retried result |
| Fetch fails with any other error | No relogin/retry — returns `None` |
| Two concurrent calls race for a refresh | Only one login call fires (single-flight via `asyncio.Lock`) |
| `_enabled` is `False` (missing credentials) | Returns `None` immediately, no DSM call attempted |
| `close()` with a held sid | Issues logout, clears `_sid` |
| `close()` with no held sid | No-op, no DSM call |

### `GET /api/system/storage` (`app/api/system.py`)

**✅ Implemented** — `tests/api/test_system_routes.py`, 2 tests, all passing. **Scenarios covered** (mocks `SynologyClient` directly rather than DSM — route-level, not integration-level):

| Scenario | Asserts |
|---|---|
| `SynologyClient.get_storage()` returns a valid `StorageState` | `200`, response body matches `StorageResponse` shape (bays, available, used, reserved) |
| `SynologyClient.get_storage()` returns `None` | `503`, `{"detail": "Synology storage data unavailable"}` |

### Next.js Proxy — `app/api/proxy/[...path]/route.ts`

Untested today, no framework in place yet (see Tooling section above). **Planned scenarios**, once Vitest is set up:

| Scenario | Asserts |
|---|---|
| Request to `/api/proxy/system/storage` | Forwards to `${BACKEND_URL}/api/system/storage` (segments correctly rejoined) |
| Any proxied request | `X-API-Key` header attached server-side from `process.env.API_KEY` — never present on the *incoming* browser request |
| Backend responds `200` with JSON | Proxy relays status + body unchanged |
| Backend responds `503` (e.g. Synology down) | Proxy relays status unchanged, not swallowed/converted |
| Request has query params | `request.nextUrl.search` forwarded onto the backend URL |

### Existing route coverage (already tested, listed for completeness)

Wishlist items, stock alerts, poll-trigger, and TradingAgents analysis routes already have route-level tests — see table in Tooling section above. Not duplicated here.
