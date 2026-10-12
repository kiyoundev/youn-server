# Issue #61: Challenges & Notes

## Potential Challenges
1. **CHECK constraint** — `ck_events_type` rejects `RESTOCK` until migration 0019 runs. Deploy order on the Pi: migration first, then the new code, or every restock insert fails.
   The constraint exists only in migrations (no `CheckConstraint` on the `Event` model), so tests that build tables from model metadata accept `RESTOCK` even without the migration. Only the live check on the Pi proves it.
2. **Duplicate sends (race)** — `process_item` does not check `in_flight`, and the scheduler never does. The frontend badge and the 429 only block manual clicks. Mitigation: `session.refresh(listing, with_for_update=True)` after the scrape and before reading the previous status; the second writer waits, re-reads `"ok"` and sends nothing.
3. **Identity-map trap** — the listing is loaded at the start of `process_item`, so a plain re-read returns the stale `"oos"`. Must use `refresh(..., with_for_update=True)`. Same trap #48 documented for the Product read.
4. **Lock order** — always lock listing, then product. Two scrapes of different listings of one product lock different listing rows, then queue on the one product row, so there is no cycle.
5. **`oos → error → ok` misses the restock** — an error overwrites `last_scrape_status`, so the transition is invisible. Accepted by decision (spec says no event on `error → ok`). Possible follow-up: an `oos_since` column preserved across errors.
6. **Double push on restock at or below target** — `RESTOCK` and `PRICE_DROP` both fire. Accepted by decision; switching to "restock only when no price drop" is a one-line change later.
7. **`in_flight` is a set, not a counter** — the first of two overlapping scrapes clears the flag early. Pre-existing, out of scope; noted only.

## Key Differences
| Aspect | Current | Target |
|--------|---------|--------|
| `events.type` values | `PRICE_DROP`, `STOCK_THRESHOLD` | plus `RESTOCK` |
| Listing read in `process_item` | `session.get`, no lock | refreshed `FOR UPDATE` in the ok path |
| Restock signal | none | per-listing `oos → ok` event and push |

## Rollback Plan
1. Revert the code (`jobs.py`, `notify.py`).
2. `DELETE FROM events WHERE type = 'RESTOCK';`, then `alembic downgrade 0018`.
3. Confirm `\d events` shows the two-value constraint and polls still run.
