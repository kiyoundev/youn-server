# Issue #17: Schema & API Contract

## API Routes

No route code changes — `GET /api/stockalerts/{alert_id}/analysis` (`app/api/stockalerts.py:198`, `list_analysis_results`) already returns `list[AnalysisResultResponse]` built via `from_attributes`. New model columns surface automatically once the schema is updated.

### `GET /api/stockalerts/{alert_id}/analysis`
- **Handler:** `app/api/stockalerts.py:199`
- **Request:** path param `alert_id`
- **Response (new fields only, additive):**
  ```json
  {
    "llm_calls": 12,
    "tokens_in": 48213,
    "tokens_out": 6104,
    "tool_calls": 5,
    "last_heartbeat_at": "2026-07-02T14:03:11Z",
    "error_reason": null
  }
  ```
  `error_reason` is `null` while `status` is `pending`/`running`/`done`; populated only when `status="failed"`.
- **Error cases:** unchanged — no new error paths introduced by this issue.

## Data Model (SQLAlchemy)

### `AnalysisResult` — new columns
```python
llm_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
tokens_in: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
tokens_out: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
tool_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
error_reason: Mapped[str | None] = mapped_column(String, nullable=True)
```

### `AnalysisResultResponse` (Pydantic) — new fields
```python
llm_calls: int
tokens_in: int
tokens_out: int
tool_calls: int
last_heartbeat_at: datetime | None
error_reason: str | None
```

## Settings (`app/core/config.py`) — new fields
```python
tradingagents_idle_timeout_seconds: int = 600   # 10 min — kill if no heartbeat this long
tradingagents_hard_cap_seconds: int = 7200      # 2h — kill regardless of heartbeat activity
```

## Subprocess Contract (stderr line format)

Heartbeat lines are logged via `logging.getLogger(__name__).info(...)`, using the script's existing default log format (`%(levelname)s:%(name)s:%(message)s` — unchanged, no `format=` override). Parent-side matching is therefore `"HEARTBEAT" in line`, not `line.startswith(b"HEARTBEAT")`.

```
INFO:__main__:HEARTBEAT llm_calls=3 tokens_in=1200 tokens_out=340 tool_calls=1
```

Parent parses `key=value` pairs after the `HEARTBEAT` token; unknown/malformed lines are ignored (logged at debug, never crash the watcher).
