# #41: Immediate First Scrape on Item/Listing Add

## PR / Branch
Not applicable — this project doesn't use git branches (solo project, direct commits to `main`, deliberate — see `[[project_local_dev_workflow]]`).

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | ⬜ Not started | [implementation.md](implementation.md) |
| Challenges | ⬜ Not started | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] Adding a real, scrapable listing triggers a background scrape completing after the add response returns, not blocking it
- [ ] That scrape writes `PriceHistory`, updates `last_price`/`last_scrape_status`, exactly like a normal scheduled cycle
- [ ] Result reaches the frontend via `#36`'s existing SSE broadcast
- [ ] An alert-crossing first scrape still triggers Pushover, same as any other scrape
- [ ] A failed first scrape sets `last_scrape_status: "error"` without blocking or failing the add
- [ ] Bulk add: each listing gets its own background scrape, bounded by `asyncio.Semaphore(3)`, genuinely concurrent (not sequential)
- [ ] "Processing" UI state (badge, spinner, empty-string cells, disabled switch) verified live for single add and bulk add
- [ ] Concurrent heavy-scrape behavior against Patchright's shared browser context verified live, not assumed

## Estimated Effort
- Implementation: **2.5 hours**
- Testing: **0.5 hours**
- **Total: ~3 hours**
