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
