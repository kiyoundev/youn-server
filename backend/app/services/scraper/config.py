NEXTDATA_PATHS: dict[str, list[str]] = {}
# Add entries when heuristic picks wrong value for a known store, e.g.:
# "ssense.com": ["props", "pageProps", "product", "price"]

# Timeouts and retry counts for the scraper stack — centralized here (matching
# frontend/src/lib/polling.ts's pattern for its own shared constant) instead of
# inlined at each call site, since several were duplicated verbatim across
# files. Note the unit split: httpx clients take *seconds*, Playwright/Patchright
# calls take *milliseconds* — named explicitly below so mixing them up is
# harder than with a bare number. These are the original values from #3's
# initial build (git history + .plan/3-scraping-layer/ checked) — no
# documented measurement or tuning behind the specific numbers, just what was
# picked at the time. Worth real tuning if a retailer's timeout behavior is
# ever profiled properly; until then, treat these as reasonable-but-arbitrary
# defaults, not evidence-backed values.

HTTP_TIMEOUT_SECONDS = 10
"""httpx AsyncClient timeout — HTTPScraper's main request, and base.py's
Shopify products.json shortcut request."""

PAGE_NAV_TIMEOUT_MS = 30_000
"""Playwright page.goto() timeout — PatchrightScraper's base get_price(), and
both of AmazonCAScraper's navigations (homepage warm-up + product page)."""

CLOUDFLARE_CHALLENGE_TIMEOUT_MS = 20_000
"""How long to wait for a Cloudflare "Just a moment..." interstitial's title
to change before giving up and extracting from whatever HTML is present."""

PRICE_LOCATOR_TIMEOUT_MS = 3_000
"""AmazonCAScraper's [data-pricetopay-label] locator text_content() wait —
short since this selector should already be in the DOM by the time it's
checked (page.goto already used wait_until="load")."""

AMAZON_MAX_RETRIES = 2
"""AmazonCAScraper.get_price()'s retry count — the only scraper in this stack
with an in-process retry loop; HTTPScraper and the base PatchrightScraper both
make a single attempt each.

Decided (not just noted) this asymmetry is fine, not extended elsewhere:
every scraper's real "retry" is the scheduled poll_prices cycle itself — a
failed attempt just waits up to 6h for the next one, same effective outcome
as an immediate in-process retry, just on a longer timescale. Amazon's extra
in-process retries exist for a narrower reason: its selectors depend on the
page having fully settled right after a fresh navigation (see the two-step
homepage-warm-up + product-page pattern in get_price() below), which is
more plausibly flaky moment-to-moment than "did the request/render succeed
at all" — the thing HTTPScraper/base PatchrightScraper's single attempt
already covers. Revisit only if a specific non-Amazon retailer shows the
same moment-to-moment flakiness Amazon's retry loop was built for."""
