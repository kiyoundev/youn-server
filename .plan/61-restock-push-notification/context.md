# Issue #61: Context

## Issue Description
When a listing that was `"oos"` becomes available again (its next scrape returns `"ok"`), send a push notification through the existing event pipeline: `jobs.py` inserts an event of a new type `RESTOCK` (alongside `PRICE_DROP` and `STOCK_THRESHOLD`), and the dispatcher's consumer sends it through `send_alert()`.

- Fire only on `oos → ok`, detected by comparing the listing's previous `last_scrape_status` against the new result. Not on a first-ever scrape, not on repeated `"oos"`, not on `error → ok`.
- Independent of the target price. The message includes the current price (product currency, #45) and the retailer.
- One notification per restock, not per scrape. A manual scrape racing a scheduled one must not double-send.
- Applies to every retailer that reports `"oos"`; same path for manual and scheduled scrapes.

Acceptance criteria: see `_index.md`.

## Component / Route Summary

### Current State
- `app/scheduler/jobs.py` `process_item`: loads the listing with a plain `session.get` (no lock), scrapes, then writes status. The `oos` branch (line ~201) and `error` branch return early; the `ok` path sets `last_scrape_status = "ok"` (line ~244), then takes a `with_for_update()` lock on the **Product** row (#48) and adds a `PRICE_DROP` `Event` if the cheapest price is at or below target. The event id is put on the queue after commit.
- `app/consumers/dispatcher.py` runs `notify.handle`, then analysis only for `STOCK_THRESHOLD`, then marks the event processed.
- `app/consumers/notify.py` `handle` branches on `event.type` (`PRICE_DROP`, `STOCK_THRESHOLD`); any other type is logged and skipped.
- `events.type` has a DB CHECK constraint `ck_events_type IN ('PRICE_DROP','STOCK_THRESHOLD')` (migration 0002), so a `RESTOCK` insert currently fails.
- Only `POST /api/items/{id}/poll` checks `in_flight` (429); `poll_prices` and `process_item` do not, so a scheduled and a manual scrape can overlap on one listing.

### Target State
- `process_item` reads the listing's previous status under a row lock and inserts a `RESTOCK` event on `oos → ok`.
- `notify.py` formats `RESTOCK`. Migration 0019 widens the CHECK constraint.
- Tests cover every transition.

## Impact & Risk

### Files Changed
- **`backend/alembic/versions/0019_events_restock_type.py`** (new) — widen `ck_events_type`.
- **`backend/app/scheduler/jobs.py`** — lock the listing in the `ok` path, capture `was_oos`, add the `RESTOCK` event and queue it after commit.
- **`backend/app/consumers/notify.py`** — `_format_restock` and a `RESTOCK` branch in `handle`.
- **`backend/tests/scheduler/test_jobs.py`** — transition tests.
- **`backend/tests/consumers/`** — formatting test for `RESTOCK` (location to confirm when implementing).
- **`.doc/issues.md`** — tick #61 once verified.

### Dependencies
- **`app/services/format.py` `format_price`** — reused for the body, same as `PRICE_DROP`.
- **`app/services/notifications.py` `send_alert`** — unchanged.
- **#48 Product row lock** — the new listing lock must be taken before it (lock order listing → product).
- **#60** (soft) — a used-only Amazon result may later count as `oos`; this issue needs no change for that.
