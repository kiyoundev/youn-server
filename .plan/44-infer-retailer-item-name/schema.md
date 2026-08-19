# Issue #44: Schema & API Contract

## Migration

**`backend/alembic/versions/0013_product_name_nullable.py`** (revises `0012`)

```python
def upgrade() -> None:
    op.alter_column("products", "name", nullable=True)


def downgrade() -> None:
    # Best-effort — any product left with name=NULL (never got a first
    # successful scrape, or user never typed one) needs a real value before
    # the NOT NULL constraint can come back, or this raises.
    op.execute("UPDATE products SET name = 'Untitled' WHERE name IS NULL")
    op.alter_column("products", "name", nullable=False)
```

Single, purely additive migration — no backfill needed on `upgrade()` (existing rows already have non-null names), only the constraint relaxes.

## `ScraperResult` (`backend/app/services/scraper/result.py`)

```python
@dataclass(frozen=True)
class ScraperResult:
    price: float | None
    status: Literal["ok", "oos", "error"]
    site_name: str | None = None
    product_title: str | None = None
```

Defaulted so every existing call site constructing a `ScraperResult` without these two fields keeps compiling — most extraction methods only ever set price/status; only the new independent name-extraction pass (and `AmazonCAScraper`) populate them.

## `BaseScraper._run_hierarchy` (`backend/app/services/scraper/base.py`)

```python
def _extract_site_name(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", property="og:site_name")
    if tag and tag.get("content"):
        return tag["content"].strip()
    # JSON-LD Organization/Brand — reuses the existing ld+json script scan,
    # a second, narrower pass (different @type target than _find_jsonld_product)
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        org = _find_jsonld_type(data, {"Organization", "Brand"})
        if org and org.get("name"):
            return str(org["name"]).strip()
    if soup.title and soup.title.string:
        # Heuristic: many sites format <title> as "Product – Site Name" or
        # "Product | Site Name" — take the tail segment after the last
        # separator as the site name guess.
        return _last_title_segment(soup.title.string)
    return None


def _extract_product_title(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", property="og:title")
    if tag and tag.get("content"):
        return tag["content"].strip()
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        product = _find_jsonld_product(data)  # already exists
        if product and product.get("name"):
            return str(product["name"]).strip()
    if soup.title and soup.title.string:
        # Heuristic: take the lead segment before the last separator —
        # inverse of _extract_site_name's tail-segment guess.
        return _first_title_segment(soup.title.string)
    return None
```

`_run_hierarchy` itself:
```python
async def _run_hierarchy(self, html: str, url: str) -> ScraperResult:
    result = await self._extract_shopify(html, url)
    soup = BeautifulSoup(html, "html.parser")  # moved up — needed unconditionally now
    if result is None:
        result = self._extract_jsonld(soup)
    if result is None:
        result = self._extract_og_price(soup)
    if result is None:
        result = self._extract_nextdata(soup, url)
    if result is None:
        result = ScraperResult(price=None, status="error")

    site_name = _extract_site_name(soup)
    product_title = _extract_product_title(soup)
    return dataclasses.replace(result, site_name=site_name, product_title=product_title)
```
`dataclasses.replace` since `ScraperResult` is frozen — cheap, avoids threading two more constructor args through every one of the 4 existing extraction methods' own `ScraperResult(...)` construction call sites.

`_last_title_segment`/`_first_title_segment`: small new helpers splitting on common separators (`–`, `—`, `|`, `-`) and returning the appropriate side, trimmed; `None` if the title has no recognizable separator (single-segment titles are ambiguous — better to return nothing than guess wrong).

`_find_jsonld_type(data, {"Organization", "Brand"})`: a small generalization of the existing `_find_jsonld_product` (which hardcodes `"Product"`) to accept a set of target `@type` values — refactor `_find_jsonld_product` to call it with `{"Product"}` rather than duplicating the recursive-search logic.

## `AmazonCAScraper.get_price` (`backend/app/services/scraper/patchright_scraper.py`)

Add one title read alongside the existing price-locator logic, non-fatal on failure (same pattern as `_find_price_text`'s own try/except):
```python
async def _find_product_title(self, page) -> str | None:
    try:
        title = await page.title()
        return title.strip() if title else None
    except Exception:
        return None
```
Called once per successful scrape in `get_price`, attached via the same `dataclasses.replace`-or-direct-construction pattern as the final `ScraperResult(...)` build there.

## `process_item` (`backend/app/scheduler/jobs.py`)

Two fill points, both guarded, both no-ops when their condition doesn't hold:

```python
# Right after a successful scrape (scrape.status == "ok", price is not None) —
# doesn't need `product` at all, only `listing` and the URL's hostname.
if scrape.site_name:
    hostname = urlparse(listing.url).hostname or ""
    if listing.retailer == _derive_retailer(hostname):
        listing.retailer = scrape.site_name

# ... later, at the existing with_for_update() locked `product` read (#48) ...
if scrape.product_title and product.name is None:
    product.name = scrape.product_title
```

## Pydantic Schemas

### `backend/app/schemas/product.py`
```python
class ProductCreate(BaseModel):
    name: str | None = None  # was: name: str
    ...

class ProductResponse(BaseModel):
    name: str | None  # was: name: str
    ...

class ListingFailure(BaseModel):
    url: str
    detail: str
    retailer: str  # new — hostname-derived, same _derive_retailer() as a real listing gets
```

### `backend/app/api/items.py`
`create_item`'s failure-collection path (wherever a `ListingFailure` is constructed — duplicate URL, in-batch collision, unscrapable) needs `retailer=_derive_retailer(_hostname_of(url))` attached. Straightforward since `_derive_retailer`/`_hostname_of` already exist and are synchronous — no scrape needed for this path (matches the issue's own note: a failed-to-scrape URL has no successful scrape to infer *from*, so this reuses the same fallback a real listing gets at creation time, not real inference).

## Frontend

### `frontend/src/lib/api/items.ts`
```typescript
export interface Product {
  ...
  name: string | null;  // was: string
  ...
}

export interface ListingFailure {
  url: string;
  detail: string;
  retailer: string;  // new
}
```

### `frontend/src/app/watchlist/page.tsx`
- Wherever `product.name` renders (table cell, sheet header, page `<title>` if used there), fall back to a placeholder (e.g. `product.name ?? "Untitled"`) for the `NULL` case.
- Bulk-add failure toast: `failed.map((f) => \`${f.retailer} (${f.detail})\`).join(", ")` — retailer name instead of the raw URL.
