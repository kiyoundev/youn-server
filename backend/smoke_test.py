"""Live smoke tests — run with: backend/.venv/bin/python3 backend/smoke_test.py"""

import asyncio
import random
import sys

import httpx

sys.path.insert(0, ".")

from app.services.scraper.base import USER_AGENTS, _build_headers
from app.services.scraper.http_scraper import HTTPScraper
from app.services.scraper.patchright_scraper import AmazonCAScraper, PatchrightScraper
from app.services.scraper.result import ScraperResult

DEBUG = "--debug" in sys.argv
HEADFUL = "--headful" in sys.argv

LIVE_URLS = {
    "shopify (deadstock.ca)": "https://deadstock.ca/products/on-x-paf-cloudboom-next-white-gale?variant=41682439569493",
    "json-ld (bestbuy.ca)": "https://www.bestbuy.ca/en-ca/product/apple-airpods-max-2-usb-c-over-ear-noise-cancelling-bluetooth-headphones-midnight/19815086",
    "nextdata (ssense.com)": "https://www.ssense.com/en-ca/men/product/salomon/brown-and-off-white-xt-whisper-sneakers/19776271",
}

AMAZON_URL = "https://www.amazon.ca/gp/aw/d/B0GSS4SGZR/"


def fmt(label: str, result: ScraperResult) -> None:
    icon = "✓" if result.status == "ok" else ("~" if result.status == "oos" else "✗")
    print(f"  {icon} {label}: status={result.status} price={result.price}")


async def probe(url: str) -> None:
    """Show raw HTTP status + which extraction signals are present."""
    ua = random.choice(USER_AGENTS)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15, http2=True) as client:
            resp = await client.get(url, headers=_build_headers(ua))
        html = resp.text
        print(f"    HTTP {resp.status_code}  ({len(html)} bytes)")

        has_shopify = "/products/" in url and "variants" in html
        has_jsonld = 'application/ld+json' in html
        has_og = 'og:price:amount' in html or 'product:price:amount' in html
        has_nextdata = '__NEXT_DATA__' in html
        print(f"    signals: shopify={has_shopify} jsonld={has_jsonld} og={has_og} nextdata={has_nextdata}")

        if resp.status_code != 200:
            snippet = html[:300].replace("\n", " ")
            print(f"    body snippet: {snippet}")
    except Exception as e:
        print(f"    exception: {type(e).__name__}: {e}")


async def run_http() -> None:
    print("\n--- HTTPScraper ---")
    scraper = HTTPScraper()
    for label, url in LIVE_URLS.items():
        result = await scraper.get_price(url)
        fmt(label, result)
        if DEBUG:
            await probe(url)


async def probe_patchright(label: str, url: str) -> None:
    """Navigate with Patchright and show what signals the rendered page has."""
    from patchright.async_api import async_playwright
    p = await async_playwright().start()
    try:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"    nav exception: {type(e).__name__}: {e}")
        html = await page.content()
        has_jsonld = 'application/ld+json' in html
        has_og = 'og:price:amount' in html or 'product:price:amount' in html
        has_nextdata = '__NEXT_DATA__' in html
        has_variants = 'variants' in html
        title_tag = (await page.title())[:80]
        print(f"    title: {title_tag}")
        print(f"    signals: jsonld={has_jsonld} og={has_og} nextdata={has_nextdata} variants={has_variants}  ({len(html)} bytes)")
        await page.close()
        await browser.close()
    finally:
        await p.stop()


async def run_patchright() -> None:
    mode = "headful" if HEADFUL else "headless"
    print(f"\n--- PatchrightScraper ({mode}) ---")
    if HEADFUL:
        from patchright.async_api import async_playwright
        from app.services.scraper.patchright_scraper import _USER_DATA_DIR
        _p = await async_playwright().start()
        PatchrightScraper._playwright = _p
        PatchrightScraper._context = await _p.chromium.launch_persistent_context(
            _USER_DATA_DIR, headless=False, locale="en-CA", timezone_id="America/Toronto"
        )
    else:
        await PatchrightScraper.start_browser()
    try:
        scraper = PatchrightScraper()
        for label, url in LIVE_URLS.items():
            result = await scraper.get_price(url)
            fmt(label, result)
            if DEBUG and result.status == "error":
                await probe_patchright(label, url)

        print("\n--- AmazonCAScraper ---")
        if DEBUG:
            from app.services.scraper.patchright_scraper import AmazonCAScraper as _AZ
            page = await PatchrightScraper._context.new_page()
            try:
                print("    navigating homepage...")
                await page.goto("https://www.amazon.ca", wait_until="domcontentloaded", timeout=30000)
                print(f"    homepage: '{await page.title()}' ({len(await page.content())} bytes)")
                print("    navigating product...")
                await page.goto(AMAZON_URL, wait_until="load", timeout=30000)
                print(f"    product:  '{await page.title()}' ({len(await page.content())} bytes)")
                scraper_debug = _AZ()
                raw = await scraper_debug._find_price_text(page)
                print(f"    _find_price_text: {raw!r}")
                # Dump all .a-offscreen elements with non-empty text to find where price actually is
                all_offscreen = await page.evaluate("""
                    () => [...document.querySelectorAll('.a-offscreen')]
                        .map(el => ({text: el.textContent.trim(), path: el.closest('[id]')?.id || '?'}))
                        .filter(x => x.text.length > 0)
                """)
                print(f"    all .a-offscreen with text ({len(all_offscreen)} found):")
                for item in all_offscreen[:10]:
                    print(f"      #{item['path']}: {item['text']!r}")
            except Exception as e:
                print(f"    exception: {type(e).__name__}: {e}")
            finally:
                await page.close()
        else:
            amazon = AmazonCAScraper()
            result = await amazon.get_price(AMAZON_URL)
            fmt("amazon.ca", result)
    finally:
        await PatchrightScraper.close_browser()


async def run_synology() -> None:
    print("\n--- SynologyClient ---")
    from app.services.synology import synology_client

    state = await synology_client.get_storage()
    if state is None:
        print("  ✗ get_storage() returned None (check .env creds / host reachable / DSM app permission)")
        return
    for bay in state.bays:
        print(f"  bay {bay.label}: {bay.status}")
    print(
        f"  available={state.available:.3f}TB used={state.used:.3f}TB reserved={state.reserved:.3f}TB"
    )


async def main() -> None:
    if "--synology" in sys.argv:
        await run_synology()
        return

    await run_http()

    run_pw = "--patchright" in sys.argv
    if run_pw:
        await run_patchright()
    else:
        print("\n  (skip Patchright — pass --patchright to include)")


asyncio.run(main())
