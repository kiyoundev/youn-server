from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.product import ProductStatus
from app.schemas.listing import ListingResponse
from app.schemas.validators import strip_name_or_none, validate_http_url


class ProductCreate(BaseModel):
    # Optional (issue #44) — left blank, Product.name stays NULL until
    # process_item fills it from the first successful scrape's inferred
    # product_title. An explicit "" (not just an omitted field) also maps to
    # None here, not stored as an empty string — a caller hitting the API
    # directly, not just the relaxed frontend form, gets the same treatment.
    name: str | None = None
    target_price: float
    # Zero or more listing URLs, created in the same request as the product
    # (bulk, not chained) — auto-detect only, no per-URL retailer/scraper_type
    # override here (those live on ListingCreate, where they're meaningful
    # against exactly one URL; a single override field doesn't make sense
    # once this is a list). A product with urls=[] gets created with zero
    # listings — same accepted state as before, just no longer the *only*
    # way to reach a listingless product.
    urls: list[str] = []

    _strip_name = field_validator("name")(strip_name_or_none)

    @field_validator("urls")
    @classmethod
    def _validate_urls(cls, value: list[str]) -> list[str]:
        for url in value:
            validate_http_url(url)
        return value


class ProductUpdate(BaseModel):
    name: str | None = None
    target_price: float | None = None
    active: bool | None = None

    # Same coercion as ProductCreate.name (issue #44 review finding) — an
    # explicit "" via PATCH must also map to None, not stay "". Without this,
    # product.name = "" would never satisfy process_item's `is None`
    # inference guard again (stuck, worse than staying NULL), and the
    # frontend's `product.name ?? "Untitled"` fallback wouldn't catch "" —
    # only null/undefined trigger `??`.
    _strip_name = field_validator("name")(strip_name_or_none)


class ProductResponse(BaseModel):
    id: int
    name: str | None
    target_price: float
    alerted_at: datetime | None
    status: ProductStatus
    last_checked: datetime | None
    listings: list[ListingResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class ListingFailure(BaseModel):
    url: str
    detail: str
    # Hostname-derived (issue #44) — same _derive_retailer() fallback a real
    # listing gets at creation time, not real inference (a failed-to-scrape
    # URL has no successful scrape to infer a display name from).
    retailer: str


class ProductCreateResponse(BaseModel):
    """POST /api/items's actual response shape — product plus whichever of
    the requested URLs didn't make it in (duplicate, in-batch collision, or
    unscrapable), so a partial success is fully representable in one
    response instead of silently dropping which URLs failed and why."""

    product: ProductResponse
    failed: list[ListingFailure] = []
