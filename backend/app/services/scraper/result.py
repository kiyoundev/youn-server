from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ScraperResult:
    price: float | None
    status: Literal["ok", "oos", "error"]
    # Issue #44 — inferred page metadata, independent of price extraction.
    # site_name feeds Listing.retailer (e.g. "Muddy George"), product_title
    # feeds Product.name (e.g. "Cayl Cap Black"). Both optional: most
    # extraction methods only ever set price/status; only BaseScraper's
    # dedicated name-extraction pass (and AmazonCAScraper's own) populate
    # these. None means "couldn't infer," never blocks price/status handling.
    site_name: str | None = None
    product_title: str | None = None
    # Issue #45 — ISO 4217 code inferred alongside site_name/product_title.
    # Unlike those two, _extract_currency always resolves to a concrete
    # currency (CAD default when no stronger signal fires) rather than
    # None — so a `None` here means the shared _run_hierarchy pass never ran
    # at all (e.g. AmazonCAScraper's own error-path ScraperResults, which
    # bypass _run_hierarchy entirely), not "couldn't infer."
    currency: Literal["USD", "CAD", "KRW"] | None = None
