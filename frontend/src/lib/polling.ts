// Shared SWR polling cadence — not a per-file choice, a deliberate repo-wide
// convention: every REST-polled (non-SSE) list in this app refreshes on the
// same interval, recorded explicitly across #10.4/#19/#30/#10.6 in
// .doc/issues.md ("same convention as #10.1/#10.4/#30", etc). Centralized
// here so changing the cadence is a one-line edit, not a grep-and-replace
// across every page that polls.
//
// Does NOT apply to /watchlist — that page deliberately has no poll
// interval at all, replaced by SSE (#36). Don't add this constant there.
export const POLL_INTERVAL_MS = 30_000;
