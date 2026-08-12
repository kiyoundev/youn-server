# Issue #10.2: Wishlist Mutations (Add / Edit / Pause / Delete)

## Delivery

- **No branch** — committed directly to `main` per user instruction.
- Source: `.doc/issues.md:878-893` (internal doc issue, not a GitHub issue).

## Task Status

| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done (backend) | [schema.md](schema.md) |
| Implementation | 🟡 Backend done (steps 1-6), frontend wiring not started (steps 7-12) | [implementation.md](implementation.md) |
| Challenges | ✅ Documented, revised twice as design evolved | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria

Derived from the doc's stated AC plus the grill-me resolution (pause/resume moved from row-level to per-listing — see `context.md` → Target State):

- [x] (backend) Add-item dialog's target endpoint (name, target price, N retailer URLs) creates the product and every listing in **one bulk request**, probing URLs concurrently — not chained per-URL calls (design revised twice; see `challenges.md`). Frontend wiring to call it still pending.
- [x] (backend) A partial add failure (e.g. one duplicate URL among several) still keeps the successfully-created product/listings and reports which URL(s) failed, via the response's `failed[]` — verified by 8 backend tests, not yet surfaced in the UI
- [ ] Inline sheet edit of name and target price PATCHes the product; table and sheet reflect it without a reload
- [ ] Inline sheet edit of a listing's URL PATCHes that listing (URL preserved, price history preserved, id preserved) without a reload
- [ ] Add-listing and remove-listing (sheet) call the real `POST`/`DELETE .../listings` routes without a reload
- [ ] Each listing has a pause/resume toggle in the sheet; toggling PATCHes `active` and the product's rolled-up status badge updates accordingly
- [ ] Deleting a product requires confirmation, then updates the table without a reload; if that product's sheet was open, the sheet closes
- [ ] Every mutation's success/failure surfaces via toast (`@base-ui/react/toast`, this repo's actual component system); a duplicate-URL 409 shows a specific message, not a generic failure
- [ ] `X-API-Key` never appears in the browser network tab for any of the above (all traffic through the proxy)

## Estimated Effort

- Implementation: **5 hours**
- Testing: **1.5 hours**
- **Total: 6.5 hours**

(Original doc estimate was ~2h against an assumed-atomic, already-complete backend contract; scope grew after grilling to include a proxy write-path, a backend schema/route extension for listing-URL edits and listingless product creation, and net-new per-listing pause UI — none of which existed before this issue. Toast UX ended up using `@base-ui/react/toast` — already a dependency, no install needed — after an initial wrong turn toward `sonner`, which isn't this repo's component system.)
