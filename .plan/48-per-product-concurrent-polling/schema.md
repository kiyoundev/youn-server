# Issue #48: Schema & Data Model

## Why this exists
Not part of the original issue text. Surfaced while planning #48's query-grouping step: `Listing.active` was going to be the grouping/filter key, but investigation showed it's only ever written in lockstep across a whole product (one Switch in the watchlist sheet, `Promise.allSettled` over every listing) — yet backend logic (`compute_status`, `process_item`'s cross-listing comparison) and several tests treat it as independently settable per listing. Confirmed with user: consolidate to `Product.active`, drop `Listing.active`.

## Migration

**`backend/alembic/versions/0012_product_active_drop_listing_active.py`** (revises `0011`)

```python
def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    # Backfill: a product is active iff it has at least one currently-active
    # listing — matches compute_status's pre-migration "all listings inactive
    # -> paused" rule exactly. Confirmed lossless via direct query before
    # writing this migration: no product today has a mixed active/inactive
    # listing set, so every product is already either fully-active or
    # fully-inactive under the old per-listing model.
    op.execute(
        """
        UPDATE products SET active = false
        WHERE id NOT IN (SELECT DISTINCT product_id FROM watch_items WHERE active = true)
        """
    )
    op.drop_column("watch_items", "active")


def downgrade() -> None:
    # Best-effort — the per-listing granularity this drops can't be
    # reconstructed; every listing comes back active=true regardless of
    # what it was before the drop (matches its parent product's state,
    # which is the strongest guarantee downgrade can offer here).
    op.add_column(
        "watch_items",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute(
        """
        UPDATE watch_items SET active = false
        WHERE product_id IN (SELECT id FROM products WHERE active = false)
        """
    )
    op.drop_column("products", "active")
```

Single migration, not split expand/contract across two deploys (unlike #24's `0009`/`0011` precedent) — justified here because the backfill was confirmed lossless ahead of time and this is a solo-maintained project with no rolling-deploy constraint (per `project_local_dev_workflow` — no branches, two compose files, deliberate).

## Model Changes

### `backend/app/models/product.py`
```python
active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
```

### `backend/app/models/watch_item.py`
Remove the `active: Mapped[bool] = mapped_column(...)` line entirely.

## API Routes

### `PATCH /api/items/{product_id}`
- **Handler:** `app/api/items.py::update_item`
- **Request:** `ProductUpdate` gains `active: bool | None = None`
- **Behavior:** `if body.active is not None: product.active = body.active` — the route's docstring already claims "Applies to all listings" (pre-existing text, previously aspirational/inaccurate since no field backed it); now true, since `active` lives only on `Product` and every listing under it is gated by it implicitly (no per-listing override left to contradict it).
- **Response:** unchanged shape (`ProductResponse`), `status` now derived from the real `active` column instead of a listings scan.

### `PATCH /api/items/{product_id}/listings/{listing_id}`
- **Handler:** `app/api/items.py::update_listing`
- **Request:** `ListingUpdate` loses `active` entirely — remove the field and its handling block (`if body.active is not None: listing.active = body.active`).
- **Response:** `ListingResponse` loses `active`.

## Pydantic Schemas

### `backend/app/schemas/product.py`
```python
class ProductUpdate(BaseModel):
    name: str | None = None
    target_price: float | None = None
    active: bool | None = None
```
`ProductResponse` unchanged in shape — `status: ProductStatus` already exposes the derived state; no need to also expose raw `active` unless a future consumer needs it.

### `backend/app/schemas/listing.py`
```python
class ListingUpdate(BaseModel):
    # active removed
    url: str | None = None
    retailer: str | None = None

class ListingResponse(BaseModel):
    id: int
    retailer: str
    url: str
    last_price: float | None
    last_scrape_status: Literal["ok", "oos", "error"] | None
    # active removed
    last_checked: datetime | None
    product_id: int
    created_at: datetime
```

## `compute_status` Contract Change

### `backend/app/services/product_status.py`
```python
def compute_status(listings: list[Listing], product_active: bool, alerted_at: datetime | None) -> ProductStatus:
    """Roll up a product's listings + its own active flag into one status.

    Priority, first match wins:
    1. Product inactive -> paused
    2. Any listing never scraped since creation -> processing
    3. Any listing errored on its last scrape -> failed
    4. Product has an active alert -> triggered
    5. Otherwise -> watching
    """
    if not product_active:
        return "paused"

    if any(listing.last_scrape_status is None for listing in listings):
        return "processing"

    if any(listing.last_scrape_status == "error" for listing in listings):
        return "failed"

    if alerted_at is not None:
        return "triggered"

    return "watching"
```
Call site (`items.py::_build_product_response`): `compute_status(product.listings, product.active, product.alerted_at)`.

Behavior for every reachable state is unchanged from today — the only states that existed before required all-or-nothing listing activity anyway (confirmed via the lossless-migration check), so no product transitions to a status it couldn't already reach.

## `jobs.py` Query/Logic Changes

### `poll_prices` grouping query
```python
result = await session.execute(
    select(Listing.id, Listing.product_id)
    .join(Product, Listing.product_id == Product.id)
    .where(Product.active == True)  # noqa: E712
)
```

### `process_item`'s early bail
Was: `if not listing or not listing.active: return`
Becomes:
```python
if not listing:
    return
product_active = (
    await session.execute(select(Product.active).where(Product.id == listing.product_id))
).scalar_one_or_none()
if product_active is not True:
    return
```
Deliberately a **column-only** select (`Product.active`, not the `Product` entity) — loading the full `Product` entity here via `session.get()` would populate the session's identity map, and the later `with_for_update()` locked load in the same function would then risk handing back that already-cached (pre-lock) instance instead of a genuinely fresh post-lock read, silently reintroducing the exact staleness this issue's race fix exists to close. A column-only select never touches the identity map.

### Cross-listing price comparison
Was: `select(Listing).where(Listing.product_id == product.id, Listing.active == True)`
Becomes: `select(Listing).where(Listing.product_id == product.id)` — no more per-listing active to filter on; every listing under an active product participates. `available_listings`'s existing `last_scrape_status == "ok"` filter is untouched (different concept — scrape health, not pause state).

## Frontend

### `frontend/src/lib/api/items.ts`
```typescript
export interface Listing {
  // active removed
  ...
}

export interface ProductUpdatePayload {
  name?: string;
  target_price?: number;
  active?: boolean;
}

export interface ListingUpdatePayload {
  // active removed
  url?: string;
}
```

### `frontend/src/app/watchlist/page.tsx`
```tsx
<Switch
  checked={product.status !== "paused"}
  disabled={product.status === "processing"}
  aria-label={product.status !== "paused" ? "Pause item" : "Resume item"}
  onCheckedChange={async (active) => {
    try {
      await updateProduct(product.id, { active });
      await mutate("/api/proxy/items");
      toast.success(active ? "Resumed" : "Paused");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Failed to update");
    }
  }}
/>
```
Replaces the `Promise.allSettled(product.listings.map(...))` fan-out and its partial-failure toast branch — one request, one outcome, no more "N of M retailers failed to update" case (that failure mode existed only because the old model wrote N independent rows for one logical action).
