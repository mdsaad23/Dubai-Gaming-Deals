"""
GulfDeals — Noon.ae scraper
Scrapes gaming laptops, CPUs, and GPUs from Noon.com/uae-en

Noon uses Cloudflare and dynamic React rendering.
This scraper uses Playwright with stealth settings + residential proxies.
Noon is less aggressive than Amazon but still detects headless browsers.

Usage:
    python scrapers/noon.py
"""

import asyncio, re, json
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from base import make_browser, human_delay, upsert_product

BASE_URL    = "https://www.noon.com"
LOCALE_PATH = "/uae-en"
AFFILIATE_PARAM = "?utm_source=gulfdeals&utm_medium=affiliate"

SEARCH_TARGETS = [
    {"query": "gaming laptop",          "category": "laptop"},
    {"query": "intel core i9",          "category": "cpu"},
    {"query": "intel core i7",          "category": "cpu"},
    {"query": "amd ryzen",              "category": "cpu"},
    {"query": "nvidia rtx graphics",    "category": "gpu"},
    {"query": "amd radeon rx graphics", "category": "gpu"},
]


def make_affiliate_url(url: str) -> str:
    return url + AFFILIATE_PARAM if "?" not in url else url + "&utm_source=gulfdeals"


def parse_aed_price(text: str) -> float | None:
    """Extract numeric AED price from strings like 'AED 5,499' or '5499.00'."""
    cleaned = text.replace(",", "").replace("AED", "").strip()
    m = re.search(r"[\d]+\.?\d*", cleaned)
    return float(m.group()) if m else None


def infer_brand(title: str, category: str) -> str:
    """Infer brand from product title."""
    brand_hints = {
        "laptop": ["ASUS","MSI","Lenovo","Acer","HP","Razer","Dell","Gigabyte","Samsung"],
        "cpu":    ["Intel","AMD"],
        "gpu":    ["NVIDIA","AMD","ASUS","MSI","Gigabyte","EVGA","Sapphire","PowerColor","Zotac"],
    }
    for brand in brand_hints.get(category, []):
        if brand.lower() in title.lower():
            return brand
    return title.split()[0]


async def accept_cookies(page):
    """Dismiss cookie banner if present."""
    try:
        btn = page.locator("button[data-qa='allow-all'], button:has-text('Accept')")
        if await btn.count():
            await btn.first.click()
            await human_delay(0.5, 1.5)
    except Exception:
        pass


async def scrape_noon_search(ctx, query: str, category: str, max_pages=3):
    """Scrape Noon search results page."""
    page = await ctx.new_page()
    results = []

    try:
        for page_num in range(1, max_pages + 1):
            url = f"{BASE_URL}{LOCALE_PATH}/search/?q={query.replace(' ', '+')}&page={page_num}"
            print(f"  → {url}")

            try:
                await page.goto(url, wait_until="networkidle", timeout=40000)
            except PWTimeout:
                print("  ✗ Timeout — skipping page")
                break

            # Dismiss cookie banner on first page
            if page_num == 1:
                await accept_cookies(page)

            # Check for block page
            page_title = await page.title()
            if "access denied" in page_title.lower() or "403" in page_title:
                print("  ✗ Blocked — rotate proxy")
                break

            await human_delay(2, 4)

            # Wait for product grid to render
            try:
                await page.wait_for_selector("[data-qa='product-block'], .productContainer", timeout=15000)
            except PWTimeout:
                print("  ✗ No products found on page — stopping")
                break

            # Noon renders product data into __NEXT_DATA__ — much more reliable than DOM scraping
            next_data = None
            try:
                next_data_raw = await page.evaluate(
                    "() => document.getElementById('__NEXT_DATA__')?.textContent"
                )
                if next_data_raw:
                    next_data = json.loads(next_data_raw)
            except Exception:
                pass

            if next_data:
                # Parse from Next.js JSON (most reliable)
                products_from_json = parse_noon_next_data(next_data, category)
                results.extend(products_from_json)
                print(f"  ✓ {len(products_from_json)} products from Next.js data")
            else:
                # Fallback: DOM scraping
                dom_products = await scrape_noon_dom(page, category)
                results.extend(dom_products)
                print(f"  ✓ {len(dom_products)} products from DOM")

            if page_num < max_pages:
                await human_delay(4, 9)

    finally:
        await page.close()

    return results


def parse_noon_next_data(data: dict, category: str) -> list:
    """
    Extract product listings from Noon's __NEXT_DATA__ JSON blob.
    Noon embeds full product data here — far more reliable than DOM scraping.
    NOTE: Noon's internal JSON structure may change — monitor for breakage.
    """
    results = []
    try:
        # Navigate to product hits — path varies by page type
        hits = (
            data.get("props", {})
                .get("pageProps", {})
                .get("initialData", {})
                .get("hits", [])
        )
        if not hits:
            # Try alternate path for some page types
            hits = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("catalog", {})
                    .get("items", [])
            )

        for item in hits:
            try:
                sku        = item.get("sku") or item.get("id", "")
                title      = item.get("name", "")
                brand      = item.get("brand", infer_brand(title, category))
                image_url  = item.get("image_keys", [None])[0]
                if image_url and not image_url.startswith("http"):
                    image_url = f"https://f.nooncdn.com/p/{image_url}z.jpg"

                # Pricing
                price_info    = item.get("price", {})
                current_price = float(price_info.get("now", price_info.get("value", 0)) or 0)
                orig_price    = float(price_info.get("was", current_price) or current_price)
                if not current_price:
                    continue

                # Rating
                rating       = float(item.get("average_rating", 0) or 0) or None
                review_count = int(item.get("reviews_count", 0) or 0)

                # URL
                slug         = item.get("url") or f"/product/{sku}/"
                product_url  = BASE_URL + LOCALE_PATH + slug

                results.append({
                    "category":       category,
                    "brand":          brand,
                    "model":          title[:200],
                    "retailer":       "noon",
                    "retailer_id":    str(sku),
                    "product_url":    product_url,
                    "affiliate_url":  make_affiliate_url(product_url),
                    "image_url":      image_url,
                    "current_price":  current_price,
                    "original_price": orig_price,
                    "specs":          {},   # enrich via detail page if needed
                    "rating":         rating,
                    "review_count":   review_count,
                    "is_available":   item.get("is_express_available", True),
                })
                print(f"    ✓ {title[:60]}... AED {current_price}")

            except Exception as e:
                print(f"    ✗ Parse error: {e}")

    except Exception as e:
        print(f"  ✗ next_data parse failed: {e}")

    return results


async def scrape_noon_dom(page, category: str) -> list:
    """
    DOM fallback: scrape product cards directly from rendered HTML.
    Used when __NEXT_DATA__ doesn't contain the expected structure.
    """
    results = []
    cards = await page.locator("[data-qa='product-block']").all()

    for card in cards:
        try:
            title_el = card.locator("[data-qa='product-name'], .productTitle")
            if not await title_el.count():
                continue
            title = await title_el.first.inner_text()

            price_el = card.locator("[data-qa='price-now'], .priceNow")
            if not await price_el.count():
                continue
            current_price = parse_aed_price(await price_el.first.inner_text())
            if not current_price:
                continue

            orig_el = card.locator("[data-qa='price-was'], .priceWas")
            orig_price = None
            if await orig_el.count():
                orig_price = parse_aed_price(await orig_el.first.inner_text())

            link_el = card.locator("a")
            href = await link_el.first.get_attribute("href") if await link_el.count() else ""
            product_url = BASE_URL + href if href.startswith("/") else href
            sku_m = re.search(r"/p/([A-Z0-9]+)/", href)
            sku = sku_m.group(1) if sku_m else href[-20:]

            img_el = card.locator("img")
            image_url = await img_el.first.get_attribute("src") if await img_el.count() else None

            results.append({
                "category":       category,
                "brand":          infer_brand(title, category),
                "model":          title[:200],
                "retailer":       "noon",
                "retailer_id":    sku,
                "product_url":    product_url,
                "affiliate_url":  make_affiliate_url(product_url),
                "image_url":      image_url,
                "current_price":  current_price,
                "original_price": orig_price or current_price,
                "specs":          {},
                "rating":         None,
                "review_count":   0,
                "is_available":   True,
            })

        except Exception as e:
            print(f"    ✗ DOM card error: {e}")

    return results


async def main():
    print("=== GulfDeals Noon.ae Scraper ===\n")
    all_products = []

    async with async_playwright() as pw:
        browser, ctx = await make_browser(pw)
        try:
            for target in SEARCH_TARGETS:
                print(f"\n[{target['category'].upper()}] Query: '{target['query']}'")
                products = await scrape_noon_search(ctx, target["query"], target["category"])
                all_products.extend(products)
                await human_delay(6, 14)

        finally:
            await ctx.close()
            await browser.close()

    # Deduplicate by retailer_id
    seen, unique = set(), []
    for p in all_products:
        key = ("noon", p["retailer_id"])
        if key not in seen:
            seen.add(key)
            unique.append(p)

    print(f"\n=== Upserting {len(unique)} unique products to Supabase ===")
    success, failed = 0, 0
    for p in unique:
        try:
            upsert_product(p)
            success += 1
        except Exception as e:
            print(f"  ✗ {p.get('model','?')[:40]}: {e}")
            failed += 1

    print(f"\n✓ Done. {success} upserted, {failed} failed.")


if __name__ == "__main__":
    asyncio.run(main())
