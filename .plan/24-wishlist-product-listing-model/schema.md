# Issue #24: Schema & API Contract

Full contract lives in `.doc/api.md` (needs its "Wishlist Items" section rewritten as part of implementation — not yet done, see [challenges.md](challenges.md)). This file is the implementation-facing breakdown.

## API Routes

### `GET /api/items`
- **Response:** `list[ProductResponse]` — bare array, no pagination wrapper (matches existing convention)
- Each product includes its nested `listings[]` and computed `status`/`last_checked`

### `GET /api/items/{product_id}`
- **Response:** `ProductResponse`
- **Error cases:** 404 if not found

### `POST /api/items`
- **Request:** `ProductCreate` — `{ name, target_price, url, retailer?, scraper_type? }`
- **Response:** `ProductResponse` (201) — with the one listing it was created with
- **Logic:**
  1. Create `Product(name, target_price)`
  2. Derive `retailer` from URL hostname (same as today's `create_item`) unless explicitly provided
  3. Same scraper-type auto-detection probe as today's `POST /api/items` (`RETAILER_MAP` → skip; explicit `scraper_type` → skip; else probe via `detect_scraper_type`)
  4. Create `Listing(url, retailer, scraper_type, product_id=product.id)`
- **Error cases:** 422 malformed URL or invalid `scraper_type`, 400 if neither scraper works, 409 if `url` already exists (any active state, across all products)

### `POST /api/items/{product_id}/listings`
- **Request:** `ListingCreate` — `{ url, retailer?, scraper_type? }` — `product_id` comes from the path, never the body
- **Response:** `ListingResponse` (201)
- **Logic:** same retailer-derivation + scraper-type probe as `POST /api/items`, attaches to the existing `product_id`
- **Error cases:** 404 if `product_id` not found, 422/400/409 same as above

### `PATCH /api/items/{product_id}`
- **Request:** `ProductUpdate` — `{ name?, target_price? }`
- **Response:** `ProductResponse`
- **Error cases:** 404 if not found
- Editing `target_price` takes effect for all listings immediately (next poll cycle re-evaluates against the new value — no separate propagation step needed since listings don't store their own target)

### `DELETE /api/items/{product_id}`
- **Response:** 204 No Content
- **Logic:** cascades to all listings and their price history
- **Error cases:** 404 if not found

### `PATCH /api/items/{product_id}/listings/{listing_id}`
- **Request:** `ListingUpdate` — `{ active? }` — pause/unpause this one listing
- **Response:** `ListingResponse`
- **Error cases:** 404 if `product_id` or `listing_id` not found, or `listing_id` doesn't belong to `product_id`

### `DELETE /api/items/{product_id}/listings/{listing_id}`
- **Response:** 204 No Content
- **Logic:** cascades to that listing's price history. If this was the product's *last remaining* listing, the now-empty `Product` is auto-deleted in the same transaction — no zero-listing products are left behind. Sibling listings under the same product are untouched when it's not the last one.
- **Error cases:** 404 if `product_id`/`listing_id` not found or mismatched
- **Frontend responsibility (not this issue, flagging for #10.2):** since this can silently delete the whole product, the "delete last listing" action needs a confirmation dialog before the request is sent — the API itself doesn't warn, it just does it.

### `GET /api/items/{product_id}/listings/{listing_id}/history?days=30`
- **Response:** `list[PriceHistoryResponse]` — unchanged shape, same route pattern as today, renested under the product/listing path
- **Error cases:** 404 if not found

## `status` Computation (server-side, in `GET /api/items` response building)

Priority order, evaluated top to bottom, first match wins:

1. **All** listings inactive → `paused`
2. Else, among active listings only: **any** `last_scrape_status == "error"` → `failed`
3. Else: `Product.alerted_at` is not `None` → `triggered`
4. Else → `watching`

`last_checked` (product-level) = `MIN` across listings of each listing's own `MAX(price_history.checked_at)` — the *stalest* listing, so a silently-broken retailer poll is visible even if a sibling listing is updating fine.

`oos` is never a product-level `status` value — it's surfaced per listing via `last_scrape_status`, independent of the roll-up above.

## New Pydantic Schemas

```python
# app/schemas/product.py
class ProductCreate(BaseModel):
    name: str
    target_price: float
    url: str
    retailer: str | None = None
    scraper_type: Literal["patchright"] | None = None

class ProductUpdate(BaseModel):
    name: str | None = None
    target_price: float | None = None

class ProductResponse(BaseModel):
    id: int
    name: str
    target_price: float
    alerted_at: datetime | None
    status: Literal["watching", "triggered", "paused", "failed"]  # computed
    last_checked: datetime | None                                  # computed
    listings: list["ListingResponse"]
    created_at: datetime
    model_config = {"from_attributes": True}
```

```python
# app/schemas/listing.py (replaces app/schemas/watch_item.py)
class ListingCreate(BaseModel):
    url: str
    retailer: str | None = None
    scraper_type: Literal["patchright"] | None = None

class ListingUpdate(BaseModel):
    active: bool | None = None

class ListingResponse(BaseModel):
    id: int
    retailer: str
    url: str
    last_price: float | None
    last_scrape_status: Literal["ok", "oos", "error"] | None
    active: bool
    last_checked: datetime | None   # computed: MAX(price_history.checked_at) for this listing
    product_id: int
    created_at: datetime
    model_config = {"from_attributes": True}
    # scraper_type intentionally omitted — write-only, used internally at poll time only (same as today)
```

## Database Changes

```python
# app/models/product.py (new)
class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    target_price: Mapped[float] = mapped_column(Float)
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    listings: Mapped[list["Listing"]] = relationship(
        "Listing", back_populates="product", cascade="all, delete-orphan"
    )
```

```python
# app/models/watch_item.py — class renamed WatchItem -> Listing, file path unchanged
class Listing(Base):
    __tablename__ = "watch_items"  # table name unchanged — no rename needed for the split

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String, unique=True)
    retailer: Mapped[str] = mapped_column(String)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_scrape_status: Mapped[str | None] = mapped_column(String, nullable=True)  # new
    scraper_type: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)  # new

    # name, target_price, alerted_at: NOT declared on the ORM model anymore, but the
    # columns still physically exist on the table post-Migration-A (dropped in Migration B)

    product: Mapped["Product"] = relationship("Product", back_populates="listings")
    price_history: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory", back_populates="watch_item", cascade="all, delete-orphan"
    )
```

New Alembic migration `0009_product_listing_split.py` (Migration A — expand only):
1. `create_table("products", id, name, target_price, alerted_at, created_at)`
2. `add_column("watch_items", "product_id", Integer, nullable=True)` (nullable initially — required for the backfill step)
3. `add_column("watch_items", "last_scrape_status", String, nullable=True)`
4. Data migration (raw SQL via `op.execute`, not ORM): `INSERT INTO products (id, name, target_price, alerted_at, created_at) SELECT id, name, target_price, alerted_at, created_at FROM watch_items`
5. `UPDATE watch_items SET product_id = id` (1:1 reuse — every pre-existing row becomes a product-of-one)
6. `SELECT setval('products_id_seq', (SELECT MAX(id) FROM products))` — advance the sequence past the reused values so new products don't collide
7. `alter_column("watch_items", "product_id", nullable=False)`
8. `create_foreign_key(..., "watch_items", "products", ["product_id"], ["id"])`
9. **`name`/`target_price`/`alerted_at` columns on `watch_items` are left untouched** — still present, just no longer declared on the `Listing` ORM class (dropped in a future Migration B, separate issue)

`downgrade()`: drop the FK, drop `product_id` and `last_scrape_status` columns from `watch_items`, drop `products` table. Reversible — no data loss on rollback since the original `watch_items` columns were never touched.
