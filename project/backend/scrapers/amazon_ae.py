"""
GulfDeals — Amazon.ae scraper
Scrapes gaming laptops, CPUs, and GPUs from Amazon.ae search results.

IMPORTANT: Amazon actively blocks scrapers. This script uses:
  - Residential rotating proxies (see base.py)
  - Random delays between requests
  - Realistic browser fingerprint via Playwright

For production, STRONGLY consider using the Amazon Product Advertising API
instead — it's free, official, and carries zero ban risk. Apply at:
https://affiliate-program.amazon.com/

Usage:
    python scrapers/amazon_ae.py
"""

import asyncio, re, json
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from base import make_browser, human_delay, upsert_product

BASE_URL = "https://www.amazon.ae"
AFFILIATE_TAG = "gulfdeals-21"   # your Amazon Associates tag

SEARCH_TARGETS = [
    {"query": "gaming laptop",  "category": "laptop"},
    {"query": "intel core i9 processor", "category": "cpu"},
    {"query": "intel core i7 processor", "category": "cpu"},
    {"query": "amd ryzen processor",     "category": "cpu"},
    {"query": "nvidia rtx graphics card","category": "gpu"},
    {"query": "amd radeon graphics card","category": "gpu"},
]


def make_affiliate_url(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}tag={AFFILIATE_TAG}"


def parse_price(text: str) -> float | None:
    """Extract numeric price from strings like 'AED 6,199.00'."""
    m = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    return float(m.group()) if m else None


def extract_specs_from_title(title: str, category: str) -> dict:
    """
    Best-effort spec extraction from product title.
    In production, scrape the product detail page for structured specs.
    """
    specs = {}
    title_lower = title.lower()

    if category == "laptop":
        # Screen size
        m = re.search(r'(\d{1,2}(?:\.\d)?)[- ]?(?:inch|")', title_lower)
        if m: specs["screen"] = f'{m.group(1)}"'
        # RAM
        m = re.search(r'(\d+)\s*gb\s*(?:ddr\d|ram|memory)', title_lower)
        if m: specs["ram"] = f'{m.group(1)}GB'
        # GPU
        for gpu in ["rtx 4090","rtx 4080","rtx 4070 ti","rtx 4070","rtx 4060","rtx 3080","rx 7900","rx 7800"]:
            if gpu in title_lower:
                specs["gpu"] = gpu.upper()
                break
        # CPU
        for cpu in ["i9-14","i9-13","i7-14","i7-13","i5-14","ryzen 9","ryzen 7","ryzen 5"]:
            if cpu in title_lower:
                specs["cpu"] = cpu.title()
                break

    elif category == "cpu":
        m = re.search(r'(i[3579]-\d{4,5}[a-z]*|ryzen \d \d{4}[a-z]*)', title_lower)
        if m: specs["model_number"] = m.group(1).upper()
        for socket in ["lga1700", "lga1851", "am5", "am4"]:
            if socket in title_lower:
                specs["socket"] = socket.upper()
                break

    elif category == "gpu":
        m = re.search(r'(\d+)\s*gb\s*(?:gddr|vram)', title_lower)
        if m: specs["memory"] = f'{m.group(1)}GB'
        for chip in ["rtx 4090","rtx 4080","rtx 4070","rtx 4060","rx 7900","rx 7800","rx 7700"]:
            if chip in title_lower:
                specs["chip"] = chip.upper()
                break

    return specs


async def scrape_search_page(ctx, query: str, category: str, max_pages=3):
    """Scrape Amazon.ae search results for a given query."""
    page = await ctx.new_page()
    results = []

    try:
        for page_num in range(1, max_pages + 1):
            url = f"{BASE_URL}/s?k={query.replace(' ', '+')}&page={page_num}"
            print(f"  → {url}")

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except PWTimeout:
                print("  ✗ Page timeout — skipping")
                break

            # Check for CAPTCHA
            if await page.locator("form[action='/errors/validateCaptcha']").count() > 0:
                print("  ✗ CAPTCHA detected — rotate proxy and retry")
                break

            await human_delay(2, 4)

            # Extract product cards
            cards = await page.locator("div[data-component-type='s-search-result']").all()
            print(f"  Found {len(cards)} products on page {page_num}")

            for card in cards:
                try:
                    # Title
                    title_el = card.locator("h2 a span")
                    if not await title_el.count():
                        continue
                    title = await title_el.first.inner_text()

                    # URL
                    link_el = card.locator("h2 a")
                    href = await link_el.first.get_attribute("href") or ""
                    product_url = BASE_URL + href if href.startswith("/") else href

                    # ASIN from URL
                    asin_m = re.search(r"/dp/([A-Z0-9]{10})", product_url)
                    asin = asin_m.group(1) if asin_m else None
                    if not asin:
                        continue

                    # Current price
                    price_whole = await card.locator(".a-price-whole").first.inner_text() if await card.locator(".a-price-whole").count() else ""
                    price_text = price_whole.strip().replace(",", "")
                    current_price = parse_price(price_text)
                    if not current_price:
                        continue  # skip items with no listed price

                    # Original price (strikethrough)
                    orig_el = card.locator(".a-price.a-text-price .a-offscreen")
                    original_price = None
                    if await orig_el.count():
                        original_price = parse_price(await orig_el.first.inner_text())

                    # Rating
                    rating_el = card.locator("span[aria-label*='stars']")
                    rating = None
                    if await rating_el.count():
                        rating_text = await rating_el.first.get_attribute("aria-label") or ""
                        m = re.search(r"([\d.]+) out of", rating_text)
                        if m: rating = float(m.group(1))

                    # Review count
                    review_el = card.locator("span[aria-label*='ratings']")
                    review_count = 0
                    if await review_el.count():
                        review_text = await review_el.first.get_attribute("aria-label") or ""
                        m = re.search(r"([\d,]+)", review_text)
                        if m: review_count = int(m.group().replace(",", ""))

                    # Image
                    img_el = card.locator("img.s-image")
                    image_url = await img_el.first.get_attribute("src") if await img_el.count() else None

                    # Brand (first word of title, roughly)
                    brand = title.split()[0] if title else "Unknown"

                    specs = extract_specs_from_title(title, category)

                    product_data = {
                        "category":       category,
                        "brand":          brand,
                        "model":          title[:200],
                        "retailer":       "amazon_ae",
                        "retailer_id":    asin,
                        "product_url":    product_url,
                        "affiliate_url":  make_affiliate_url(f"{BASE_URL}/dp/{asin}"),
                        "image_url":      image_url,
                        "current_price":  current_price,
                        "original_price": original_price or current_price,
                        "specs":          specs,
                        "rating":         rating,
                        "review_count":   review_count,
                        "is_available":   True,
                    }

                    results.append(product_data)
                    print(f"    ✓ {title[:60]}... AED {current_price}")

                except Exception as e:
                    print(f"    ✗ Error parsing card: {e}")
                    continue

            # Respect rate limits between pages
            if page_num < max_pages:
                await human_delay(4, 9)

    finally:
        await page.close()

    return results


async def main():
    print("=== GulfDeals Amazon.ae Scraper ===\n")
    all_products = []

    async with async_playwright() as pw:
        browser, ctx = await make_browser(pw)
        try:
            for target in SEARCH_TARGETS:
                print(f"\n[{target['category'].upper()}] Query: '{target['query']}'")
                products = await scrape_search_page(ctx, target["query"], target["category"])
                all_products.extend(products)
                await human_delay(5, 12)  # longer pause between queries

        finally:
            await ctx.close()
            await browser.close()

    # Upsert all products into Supabase
    print(f"\n=== Upserting {len(all_products)} products to Supabase ===")
    success, failed = 0, 0
    for p in all_products:
        try:
            pid = upsert_product(p)
            success += 1
        except Exception as e:
            print(f"  ✗ DB error for {p.get('model','?')[:40]}: {e}")
            failed += 1

    print(f"\n✓ Done. {success} upserted, {failed} failed.")


if __name__ == "__main__":
    asyncio.run(main())
