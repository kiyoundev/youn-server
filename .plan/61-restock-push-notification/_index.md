# Issue #61: Push Notification on Restock (Out-of-Stock → In-Stock)

## PR / Branch
- **Branch:** `feature/61-restock-push-notification`
- **PR Title:** `main | feature - 61 - Restock push notification`
- **Note:** this repo commits straight to `main` (solo project); branch/PR fields are nominal.

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ⬜ Not started | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] `oos → ok` inserts one `RESTOCK` event and one push is sent, with product, retailer and current price
- [ ] No event on a first scrape, repeated `"oos"`, `error → ok`, `oos → error → ok`, or `ok → ok`
- [ ] Manual and scheduled scrapes racing on the same listing send one push, not two (row lock on the listing)
- [ ] A restock at or below target sends both `RESTOCK` and `PRICE_DROP` (independent events)
- [ ] A restock fires per listing, even when another listing of the product is already `ok`
- [ ] Migration widens `ck_events_type` to include `RESTOCK`
- [ ] Test coverage in `test_jobs.py` for each transition, plus a `notify.py` formatting test
- [ ] Live-verified with an IKEA listing (or a simulated `oos → ok` flip)

## Estimated Effort
- Implementation: **1.5 hours**
- Testing: **1 hour**
- Live verification: **0.5 hours**
- **Total: ~3 hours**
