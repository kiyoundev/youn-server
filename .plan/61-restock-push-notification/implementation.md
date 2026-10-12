# Issue #61: Implementation

## Steps

### 1. Migration
- [x] `0019_events_restock_type.py` — widen `ck_events_type` (see `schema.md`)
- [x] Run the migration locally and check `\d events` (upgrade, insert, downgrade round trip all verified)

### 2. Notify consumer
- [x] `notify.py` — add `_format_restock(event, session)` and a `RESTOCK` branch in `handle`

### 3. Scheduler
- [x] `jobs.py` `process_item` ok path — before setting `last_scrape_status`, `await session.refresh(listing, with_for_update=True)` and capture `was_oos = listing.last_scrape_status == "oos"`. Add a comment on the identity-map trap (same as #48) and the listing → product lock order.
- [x] After the Product locked read and the `PRICE_DROP` block, if `was_oos`, add the `RESTOCK` `Event` (payload per `schema.md`). Commit once, then `queue.put` each new event id (restock and price drop are independent).
- [x] Log `RESTOCK: listing %d (%s) ...` at INFO

### 4. Tests (`tests/scheduler/test_jobs.py`, `tests/consumers`)
- [x] `oos → ok` inserts one `RESTOCK` event and queues its id
- [x] First scrape (`None → ok`) inserts none
- [x] `oos → oos` inserts none
- [x] `error → ok` inserts none
- [x] `ok → ok` inserts none
- [x] `oos → error → ok` inserts none (documents the known limitation)
- [x] Restock above target: `RESTOCK` only; restock at or below target: `RESTOCK` and `PRICE_DROP`
- [x] Restock while a sibling listing is `ok`: still fires
- [x] Duplicate-send guard: `refresh(listing, with_for_update=True)` is awaited once (mock-level only; real concurrency is proven in the live step)
- [x] `notify` formats title, body, URL, priority 0, and uses the product currency

### 5. Live verification
- [x] Apply migration 0019 on the Pi before deploying the code
- [x] Simulate `oos → ok`: set an IKEA listing's `last_scrape_status = 'oos'` in the DB, trigger a manual scrape, confirm one push and one `RESTOCK` event row with status `processed`
- [x] Trigger a second manual scrape: no further push

### 6. Cleanup
- [x] Run `backend/.venv/bin/python -m pytest tests -q`
- [x] Tick #61 in `.doc/issues.md`, note the `oos → error → ok` limitation
