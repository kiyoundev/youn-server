# Issue #45: Schema & API Contract

## Data Model

### `Product.currency` (new column)
```python
# backend/app/models/product.py
currency: Mapped[str | None] = mapped_column(String, nullable=True)
```
Nullable, ISO 4217 code, app-constrained to `Literal["USD", "CAD", "KRW"]` at the Pydantic
layer (no DB CHECK constraint — same looseness as other string-typed fields in this codebase,
e.g. `Listing.retailer`). NULL means "not yet resolved" — same semantics as
`Product.name is None` (#44): fill-only-if-null from scrape inference, explicit user PATCH
always overwrites regardless of current value.

### Migration
`backend/alembic/versions/0014_product_currency.py` (next sequence number after `0013`):
```python
def upgrade() -> None:
    op.add_column("products", sa.Column("currency", sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column("products", "currency")
```
No backfill — existing rows are sample/mock data (product owner confirmed acceptable), start
NULL, resolve on next scrape cycle same as any newly-created product.

### `ScraperResult.currency` (new field)
```python
# backend/app/services/scraper/result.py
@dataclass(frozen=True)
class ScraperResult:
    price: float | None
    status: Literal["ok", "oos", "error"]
    site_name: str | None = None
    product_title: str | None = None
    currency: Literal["USD", "CAD", "KRW"] | None = None
```

## API Routes

### `POST /api/items` (existing route, extended)
- **Handler:** `backend/app/api/items.py`
- **Request:** `ProductCreate` gains optional `currency: Literal["USD","CAD","KRW"] | None`
- **Response:** `ProductCreateResponse.product.currency`

### `PATCH /api/items/{id}` (existing route, extended)
- **Handler:** `backend/app/api/items.py`
- **Request:** `ProductUpdate` gains optional `currency: Literal["USD","CAD","KRW"] | None` —
  present-and-non-null always overwrites (manual override wins over prior auto-detection)
- **Response:** `ProductResponse.currency`

### `GET /api/items` (existing route, extended)
- **Response:** each `ProductResponse.currency`

## Pydantic Schemas
```python
# backend/app/schemas/product.py
from typing import Literal

Currency = Literal["USD", "CAD", "KRW"]

class ProductCreate(BaseModel):
    ...
    currency: Currency | None = None   # optional at creation; usually left to auto-detect

class ProductUpdate(BaseModel):
    ...
    currency: Currency | None = None   # PATCH with a value = explicit override

class ProductResponse(BaseModel):
    ...
    currency: Currency | None
```

## Frontend Types
```typescript
// frontend/src/lib/api/items.ts
type Currency = "USD" | "CAD" | "KRW";

interface Product {
  // ...existing fields
  currency: Currency | null;
}

interface FxRates {
  rates: Record<string, number>; // {"USD": 1.35, "KRW": 0.00098}
  stale: boolean;
  fetchedAt: string | null;
}
```

## FX Rates

### `FxRate` model (new)
```python
# backend/app/models/fx_rate.py
class FxRate(Base):
    __tablename__ = "fx_rates"

    currency: Mapped[str] = mapped_column(String, primary_key=True)  # "USD" | "KRW"
    rate_to_cad: Mapped[float] = mapped_column(Float)  # 1 unit of `currency` = rate_to_cad CAD
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```
Two rows total (`USD`, `KRW`) — `CAD` needs no row, its rate is always 1.0.

### Migration
`backend/alembic/versions/0015_fx_rates.py`:
```python
def upgrade() -> None:
    op.create_table(
        "fx_rates",
        sa.Column("currency", sa.String(), primary_key=True),
        sa.Column("rate_to_cad", sa.Float(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )

def downgrade() -> None:
    op.drop_table("fx_rates")
```

### `backend/app/services/fx.py` (new)
```python
async def fetch_fx_rates() -> dict[str, float]:
    """Calls api.frankfurter.dev once: GET /v1/latest?base=CAD&symbols=USD,KRW
    (host corrected 2026-08-20 — api.frankfurter.app now 301-redirects here,
    which broke every scheduled refresh live in production before the fix,
    since httpx doesn't follow redirects by default; see challenges.md #7a)
    (verified live 2026-08-20). `from`/`base` accepts a single currency
    only — `from=USD,KRW` 404s ("not found"), confirmed against the live
    API. `to`/`symbols` is the one that accepts a CSV list, so the single
    request has to run CAD-as-base and invert the result:

        {"base": "CAD", "rates": {"USD": 0.7209, "KRW": 1003.11}}
        -> rate_to_cad["USD"] = 1 / 0.7209  = 1.3872
        -> rate_to_cad["KRW"] = 1 / 1003.11 = 0.0009969

    Returns {"USD": rate, "KRW": rate}, each already inverted to "1 unit
    of that currency in CAD" (matches FxRate.rate_to_cad's contract)."""

async def refresh_fx_rates(session) -> None:
    """Fetches + upserts both FxRate rows. Called by the daily scheduler job,
    and once more at app startup (best-effort — narrows the empty-table
    window to "startup fetch also failed," not "wait for the first daily
    tick"). On fetch failure: logs and returns without touching existing
    rows — last-known rate stays in place (staleness handled at read time,
    not write time)."""
```

### `GET /api/fx-rates` (new route)
- **Handler:** `backend/app/api/fx.py`
- **Response:**
```python
class FxRatesResponse(BaseModel):
    rates: dict[str, float]      # {"USD": 1.35, "KRW": 0.00098} — CAD implicit 1.0
    stale: bool                  # True if fetched_at older than 24h for either row,
                                  # or a row is entirely missing (never fetched yet)
    fetched_at: datetime | None  # oldest of the two fetched_at values; None if no rows yet
```
Read-only, served from the `fx_rates` table — never calls the upstream FX source inline at request
time, so a page load is never coupled to that service's uptime/latency.

**Bootstrap case (table empty — first boot, or `refresh_fx_rates` has never once
succeeded):** `rates` comes back `{}`, `stale: true`, `fetched_at: null`. This is a normal,
expected response shape, not an error — the frontend's `toCad()` must treat a missing key in
`rates` as "can't convert" (return `null`), never index into `rates` and propagate `undefined *
number = NaN`. See implementation.md step 5.

## Currency Detection (`backend/app/services/scraper/base.py`)

**Design basis, corrected 2026-08-20:** the issue's original motivating example
(`.doc/issues.md`) misattributed `muddygeorge.com` as the Korean/KRW site — it's actually
Canadian (CAD), on a `.com` domain. The real Korean/KRW site is `goyowear.kr`, whose actual
regression fixture (`backend/tests/scraper/test_base.py:513-514`) has **no `priceCurrency` field
in its JSON-LD and no `₩`/`원` symbol at all** — bare `"price": "388000"`. So metadata/symbol
detection alone would miss this real site; TLD is load-bearing here, not a nice-to-have (and the
prior draft's `.co.kr` string wouldn't even have matched `.kr` — fixed below). Conversely,
`muddygeorge.com` being Canadian on a `.com` domain shows TLD can't reliably split USD vs. CAD —
so that split is dropped in favor of a flat CAD default.

New `_extract_currency(soup, url, jsonld_scripts) -> Currency | None`, priority order:
1. `og:price:currency` meta / JSON-LD `Offer.priceCurrency` — explicit ISO code, direct match
   against `{"USD", "CAD", "KRW"}` (case-insensitive), else ignored (not one of the 3 supported)
2. Marked symbol/text adjacent to the price: `₩` or `원` → KRW; `US$` → USD (`C$`/`CDN$` no
   longer need their own branch — CAD is the default below anyway)
3. `.kr` TLD (matches `goyowear.kr`; also covers `.co.kr`) → KRW — needed because the real
   Korean site in this codebase doesn't mark currency on-page at all
4. Everything else (bare `$`, no signal, non-`.kr` TLD) → default `CAD`

Note: this function no longer returns `None` for the no-signal case — CAD is a resolved answer,
not "couldn't infer." `None` is now reserved for genuine extraction failure (e.g. no price found
at all upstream), consistent with `ScraperResult.currency`'s type still being `Currency | None`
for that narrower reason.

`AmazonCAScraper` bypasses this — hardcodes `currency="CAD"` on its own `ScraperResult`, not
because CAD needs special-casing (it's the default now) but because `AmazonCAScraper` runs its
own dedicated Playwright-locator extraction path and never calls `_run_hierarchy`/
`_extract_currency` at all (see context.md — same reason it needs its own product-title
extraction).
