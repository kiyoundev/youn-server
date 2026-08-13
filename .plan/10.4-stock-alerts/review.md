# #10.4: Review

## AI Review
<!-- Populated by running `/code-reviewer` before the final commit -->

**Code Review — #10.4/#10.6 staged changes**

**Intent:** Backend route rename (`/api/stocks` → `/api/stockalerts`) plus a full rebuild of `/market/[ticker]`'s alarm sheet — two-section (above/below) draft-until-Save alert management, replacing an earlier per-field-immediate-commit design — alongside a large batch of doc corrections tracking several mid-implementation design pivots this session.

**Overall assessment:** Core work (backend rename, the Sheet/draft/Save-Cancel redesign) is solid, well-reasoned, and consistent with the extensive design discussion behind it. Two real issues need fixing before merge, both concrete, not style nits.

**Critical:** None.

**Major:**
1. **Missing price validation — regression from the pre-refactor code.** `saveSection`/`isSectionDirty` (`market/[ticker]/page.tsx`, new) never check that a filled-in price is a valid positive number before firing `createStockAlert`/`updateStockAlert`. The version this replaced explicitly guarded `if (!(target_price > 0)) return;` before every mutation — that check didn't make it into the new `saveSection`. Concretely: `isSectionDirty` treats any non-empty string as dirty (`draft.target_price.trim() !== ""`), and `Number("abc")` → `NaN` — `NaN !== alert.target_price` is always true, so an invalid price registers as dirty and gets sent. `JSON.stringify(NaN)` serializes to `null`, so the backend receives `target_price: null` against a schema expecting float, surfacing as a generic "Failed to save alert" toast rather than being caught client-side. **Fix:** reject non-finite/non-positive values in `isSectionDirty`'s create branch and `saveSection` before firing.
2. **`portfolio/page.tsx` — leftover scratch code, contradicts this session's own #10.6 decision.** The staged diff adds `useSWR<StockAlert[]>("/api/proxy/stockalerts", fetcher)` plus a `console.log(stocks)` — but `stocks` is never rendered anywhere, and per #10.6 (documented at length in `issues.md`/`.plan/10.4-stock-alerts/*` this same session), the Watchlist tile is specifically supposed to never read StockAlert data — it should read `/api/proxy/watchlist` + `/api/proxy/market/quotes` instead. This block reads like debugging scratch work from earlier in the session that got staged by accident, not real progress toward either issue. Also missing `refreshInterval` (doesn't use the `POLL_INTERVAL_MS` constant just introduced this session) and has unused `error`/`isLoading` — already flagged by lint. **Recommend dropping this block entirely** rather than fixing it in place, since it shouldn't exist per the architecture decided this session.

**Minor:**
- `market/[ticker]/page.tsx:29` — `Icon` imported from `lucide-react`, never used (lint error, flagged earlier, still present).
- `watchlist/page.tsx:615` — `console.log(products)`, debug leftover, unrelated to this issue's scope, shouldn't ship.
- `lib/api/stock-alerts.ts` — two stale comments: one references the old filename `stocks.py:172` (renamed to `stock_alerts.py`), and another says "the alarm dialog's mutation handlers" (a mid-session correction — it's a Sheet now, not a Dialog).

**Praise:**
- `draftFromAlert`/`isSectionDirty`/`saveSection` as pure, side-effect-free functions — genuinely easy to unit-test whenever #29 lands a test runner, no React/DOM coupling.
- The delete-clears-stale-draft fix (clearing that section's draft on successful delete) — a real, non-obvious bug caught and fixed before it shipped, not just theoretical.
- Deliberate, readable comment on the reset-on-sheet-open effect — explains exactly why `aboveAlert`/`belowAlert` are excluded from deps (don't stomp an in-progress draft on background revalidation), not a lazy suppression.
- Backend rename re-verified against the full test suite (278 passing) — safe rename, not just claimed from the diff alone.
- Consistent citation of real precedent (`watchlist/page.tsx` line numbers) throughout comments explaining why Sheet over Dialog, matching an actually-existing pattern rather than inventing a new one.

**Questions:**
- Is `portfolio/page.tsx`'s leftover fetch+console.log intentional in-progress scratch work you want kept staged for now, or should it just be reverted before this commits?
- Any intent to add client-side price validation beyond relying on the backend, or is surfacing that as a generic toast acceptable?

**Verdict:** Request Changes. Both Major items are small to fix — the validation gap (a few lines) and the `portfolio/page.tsx` cleanup (delete, not fix). Nothing here questions the overall design; the Sheet/draft/Save-Cancel rework itself is ready.

---

## Tech Lead Review
<!-- Populated when PR review comments arrive -->

| # | Comment | File / Line | Status |
|---|---------|-------------|--------|
