# Issue #9: Schema & API Contract

## API Routes

### `POST /api/stocks` (modified)
- **Handler:** `app/api/stocks.py::create_stock_alert`
- **Request:** existing `{ ticker, target_price, direction, run_analysis? }` + new optional fields:
  ```
  deep_think_llm?: string
  quick_think_llm?: string
  anthropic_effort?: "high" | "medium" | "low"
  max_debate_rounds?: int
  max_risk_discuss_rounds?: int
  analysts?: ("market" | "social" | "news" | "fundamentals")[]
  ```
- **Response:** `StockAlertResponse` with the same new fields, `analysts` returned as a list (stored as CSV internally).
- **Error cases:** unchanged (400 invalid ticker, 409 duplicate ticker+direction).

### `PATCH /api/stocks/{alert_id}` (modified)
- **Handler:** `app/api/stocks.py::update_stock_alert`
- **Request:** existing fields + the same 6 new optional fields as `POST`, each independently settable back to `null` to revert to the global default.
- **Response:** `StockAlertResponse`.
- **Error cases:** unchanged (404, 409).

### `POST /api/stocks/{alert_id}/analyze` (modified)
- **Handler:** `app/api/stocks.py::analyze_stock_alert`
- **Change:** after creating the `AnalysisResult(status="pending")` row and committing (so `.id` exists), spawns `trading_agents.run_analysis(alert, analysis.id)` as a background `asyncio.Task` before returning.
- **Response:** unchanged shape (`AnalysisResultResponse`, `status="pending"`), still returns immediately — status transitions happen out-of-band.
- **Error cases:** unchanged (404 alert not found, 409 already running for this ticker).

### `GET /api/stocks/{alert_id}/analysis` (unchanged)
- No contract changes; `AnalysisResultResponse.stop_loss` is removed (see below).

### `GET /api/analysis/tradingagents/version` (new)
- **Handler:** `app/api/analysis.py::get_tradingagents_version`
- **Request:** none.
- **Response (cloned):**
  ```json
  {
    "current_commit": "abc1234",
    "current_date": "2026-06-15T10:00:00Z",
    "latest_commit": "def5678",
    "latest_date": "2026-06-28T14:00:00Z",
    "behind_count": 3,
    "update_available": true
  }
  ```
- **Response (not cloned):** `{ "available": false }`
- **Error cases:** none beyond the not-cloned case — `git fetch` failures (e.g. no network) are caught and logged, endpoint returns `{ "available": false, "error": "..." }` rather than 500, since this is a status-check endpoint that shouldn't break the dashboard on a transient network blip.

### `POST /api/analysis/tradingagents/update` (new)
- **Handler:** `app/api/analysis.py::update_tradingagents`
- **Request:** none.
- **Response:**
  ```json
  {
    "success": true,
    "new_commit": "def5678",
    "output": "<combined git pull + pip install stdout/stderr>"
  }
  ```
- **Error cases:** `{ "success": false, "new_commit": null, "output": "<error text>" }` on `git pull` or `pip install` failure — not a 500; the caller (dashboard) needs to display *why* it failed, not just that it did.
- **Note:** protected by the same `X-API-Key` dependency as every other router; trusts upstream `TauricResearch/tradingagents` — only call when an update is actually expected (per issue text).

## TypeScript Interfaces
<!-- .doc/api.md — update alongside the Python schema changes -->
```typescript
export interface StockAlert {
  id: number;
  ticker: string;
  target_price: number;
  direction: "above" | "below";
  last_price: number | null;
  alerted_at: string | null;
  active: boolean;
  run_analysis: boolean;
  deep_think_llm: string | null;
  quick_think_llm: string | null;
  anthropic_effort: "high" | "medium" | "low" | null;
  max_debate_rounds: number | null;
  max_risk_discuss_rounds: number | null;
  analysts: ("market" | "social" | "news" | "fundamentals")[] | null;
  created_at: string;
}

export interface AnalysisResult {
  id: number;
  stock_alert_id: number;
  event_id: number | null;
  ticker: string;
  triggered_price: number | null;
  result: Record<string, unknown> | null;
  status: "pending" | "running" | "done" | "failed";
  action: string | null; // TradingAgents rating: Buy/Overweight/Hold/Underweight/Sell
  price_target: number | null;
  report_path: string | null; // absolute path on the Pi host, e.g. /opt/tradingagents/data/reports/ENB.TO_20260701_204857
  created_at: string;
  completed_at: string | null;
}

export interface TradingAgentsVersion {
  available?: false;
  error?: string;
  current_commit?: string;
  current_date?: string;
  latest_commit?: string;
  latest_date?: string;
  behind_count?: number;
  update_available?: boolean;
}
```

## External API Contracts

- **TradingAgents wrapper subprocess** (`backend/scripts/run_tradingagents.py`, run via `/opt/tradingagents/.venv/bin/python`) — not a network API, but the contract between `services/trading_agents.py` and this script is load-bearing:
  - **Invocation:** `<venv-python> run_tradingagents.py <ticker> <trade_date:YYYY-MM-DD> --analysts market,social,news,fundamentals` with env `PYTHONPATH=/opt/tradingagents` plus any per-alert `TRADINGAGENTS_*` overrides.
  - **stdout contract:** exactly one line of JSON on success, nothing else — all library logging (`langgraph`, `httpx`, etc.) must be routed to stderr so it can't corrupt the parse. Shape:
    ```json
    {
      "decision": "Buy",
      "price_target": 123.45,
      "executive_summary": "...",
      "final_trade_decision": "<full markdown>",
      "market_report": "...",
      "sentiment_report": "...",
      "news_report": "...",
      "fundamentals_report": "...",
      "report_path": "/opt/tradingagents/data/reports/ENB.TO_20260701_204857"
    }
    ```
    `price_target` and `executive_summary` are both regex-extracted from the `**Price Target**:`/`**Executive Summary**:` lines in `final_trade_decision` — the structured `PortfolioDecision` object (which also has an `investment_thesis` field) isn't exposed through `propagate()`'s return values, only its rendered markdown. `investment_thesis` isn't pulled out as its own key since nothing consumes it separately — it's already present in full within `final_trade_decision`.

    `report_path` comes from `TradingAgentsGraph.save_reports(final_state, ticker)` — a public method the library ships specifically for programmatic callers ("Programmatic callers get the same on-disk reports the CLI produces"), so the wrapper writes the same markdown report tree (`complete_report.md` + per-section files) the interactive CLI does, at `<TRADINGAGENTS_RESULTS_DIR>/reports/<ticker>_<timestamp>/`. `TRADINGAGENTS_RESULTS_DIR` is set to `/opt/tradingagents/data`, inside the already-mounted volume, so the path is stable across container restarts and browsable directly on the Pi host filesystem.
  - **Exit code:** non-zero on any failure (import error, missing API key, `propagate()` exception) — caller treats non-zero exit or a JSON-parse failure identically: `status = "failed"`.
  - **stderr:** captured and logged on failure for debugging; discarded on success.
