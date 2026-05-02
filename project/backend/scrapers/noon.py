"""
GulfDeals — Noon.ae scraper
Scrapes gaming laptops, CPUs, and GPUs from Noon.com/uae-en

Strategy:
  1. Search pages → parse __NEXT_DATA__ JSON (most reliable) or DOM fallback
  2. Product detail pages → extract full specs, seller info, reviews
  3. Enrich with spec_parser

Noon uses Cloudflare + React SSR. Residential proxies strongly recommended.

Usage:
    cd project/backend/scrapers
    python noon.py
"""

import asyncio, re, json, sys, os
from typing import Optional
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base import (
    make_browser, human_delay, micro_delay, scroll_to_bottom,
    bulk_upsert_products, log, async_retry, parse_aed_price,
)
from spec_parser import parse_specs, infer_tags

BASE_URL    = "https://www.noon.com"
LOCALE_PATH = "/uae-en"
CDN_BASE    = "https://f.nooncdn.com/p/"

# UTM params for affiliate tracking
AFFILIATE_PARAMS = "?utm_source=gulfdeals&utm_medium=affiliate&utm_campaign=deals"

SEARCH_TARGETS = [
    # Laptops
    {"query": "gaming laptop",                    "category": "laptop"},
    {"query": "ASUS ROG gaming laptop",           "category": "laptop"},
    {"query": "MSI gaming laptop",                "category": "laptop"},
    {"query": "Lenovo Legion laptop",             "category": "laptop"},
    # CPUs — Intel
    {"query": "Intel Core i9 processor",          "category": "cpu"},
    {"query": "Intel Core i7 processor",          "category": "cpu"},
    {"query": "Intel Core i5 processor",          "category": "cpu"},
    # CPUs — AMD
    {"query": "AMD Ryzen 9 processor",            "category": "cpu"},
    {"query": "AMD Ryzen 7 processor",            "category": "cpu"},
    {"query": "AMD Ryzen 5 processor",            "category": "cpu"},
    # GPUs — NVIDIA
    {"query": "NVIDIA RTX 4090 graphics card",    "category": "gpu"},
    {"query": "NVIDIA RTX 4080 graphics card",    "category": "gpu"},
    {"query": "NVIDIA RTX 4070 graphics card",    "category": "gpu"},
    {"query": "NVIDIA RTX 4060 graphics card",    "category": "gpu"},
    # GPUs — AMD
    {"query": "AMD Radeon RX 7900 graphics card", "category": "gpu"},
    {"query": "AMD Radeon RX 7800 graphics card", "category": "gpu"},
    {"query": "AMD Radeon RX 7600 graphics card", "category": "gpu"},
]

MAX_SEARCH_PAGES = 3


def make_affiliate_url(path: str) -> str:
    """Build a Noon product URL with affiliate tracking parameters."""
    clean = path.rstrip("/")
    if "?" in clean:
        return clean + "&utm_source=gulfdeals&utm_medium=affiliate"
    return clean + AFFILIATE_PARAMS


def build_product_url(slug: str) -> str:
    if slug.startswith("http"):
        return slug
    if not slug.startswith("/"):
        slug = "/" + slug
    return BASE_URL + LOCALE_PATH + slug


def build_image_url(key: str) -> Optional[str]:
    """Convert Noon image key to CDN URL."""
    if not key:
        return None
    if key.startswith("http"):
        return key
    # Format: n/abc/xyz.jpg → https://f.nooncdn.com/p/n/abc/xyzz.jpg
    return f"{CDN_BASE}{key}z.jpg"


def infer_brand(title: str, category: str) -> str:
    brands = {
        "laptop": ["ASUS", "MSI", "Lenovo", "Acer", "HP", "Razer", "Dell",
                   "Gigabyte", "Samsung", "LG", "Huawei", "Honor"],
        "cpu":    ["Intel", "AMD"],
        "gpu":    ["ASUS", "MSI", "Gigabyte", "EVGA", "Sapphire", "PowerColor",
                   "Zotac", "XFX", "PNY", "Colorful", "Gainward", "Palit",
                   "Inno3D", "NVIDIA", "AMD"],
    }
    for brand in brands.get(category, []):
        if brand.lower() in title.lower():
            return brand
    return title.split()[0] if title.split() else "Unknown"


# ─── Cookie / consent helpers ─────────────────────────────────────────────────

async def accept_cookies(page):
    """Dismiss any cookie/consent banners."""
    for selector in [
        "button[data-qa='allow-all']",
        "button:has-text('Accept All')",
        "button:has-text('Accept')",
        "#onetrust-accept-btn-handler",
    ]:
        try:
            el = page.locator(selector)
            if await el.count():
                await el.first.click()
                await micro_delay()
                break
        except Exception:
            pass


# ─── Search page scraping ─────────────────────────────────────────────────────

@async_retry(max_attempts=2, backoff_base=4.0, exceptions=(PWTimeout, Exception))
async def scrape_search_page(ctx, query: str, category: str, page_num: int = 1) -> list[dict]:
    """Scrape one page of Noon search results. Returns list of basic product dicts."""
    url = f"{BASE_URL}{LOCALE_PATH}/search/?q={query.replace(' ', '+')}&page={page_num}"
    page = await ctx.new_page()
    items = []

    try:
        log.info("  GET %s", url)
        await page.goto(url, wait_until="networkidle", timeout=45000)

        if page_num == 1:
            await accept_cookies(page)

        # Block detection
        page_title = await page.title()
        if any(x in page_title.lower() for x in ["access denied", "403", "security check"]):
            log.warning("  ✗ Blocked by Cloudflare for query '%s'", query)
            return []

        await human_delay(1.5, 3.0)

        # Trigger lazy loading
        await scroll_to_bottom(page, steps=4)
        await human_delay(1.0, 2.0)

        # Primary: parse __NEXT_DATA__ (much more reliable than DOM)
        next_data_raw = await page.evaluate(
            "() => document.getElementById('__NEXT_DATA__')?.textContent"
        )
        if next_data_raw:
            try:
                next_data = json.loads(next_data_raw)
                items = _parse_next_data(next_data, category)
                if items:
                    log.info("  ✓ %d products from __NEXT_DATA__ on page %d", len(items), page_num)
                    return items
            except json.JSONDecodeError:
                log.warning("  ✗ __NEXT_DATA__ JSON parse failed")

        # Fallback: DOM scraping
        items = await _scrape_dom(page, category)
        log.info("  ✓ %d products from DOM on page %d", len(items), page_num)

    except PWTimeout:
        log.warning("  ✗ Timeout on Noon search page %d for query '%s'", page_num, query)
    finally:
        await page.close()

    return items


def _parse_next_data(data: dict, category: str) -> list[dict]:
    """
    Extract product listings from Noon's __NEXT_DATA__ JSON blob.
    Noon embeds full catalog data here — more complete than DOM.
    NOTE: Structure may change between Noon deployments — monitor for breakage.
    """
    items = []

    # Try several possible paths for the hits array
    hits = None
    paths_to_try = [
        ["props", "pageProps", "initialData", "hits"],
        ["props", "pageProps", "catalog", "items"],
        ["props", "pageProps", "data", "hits"],
        ["props", "pageProps", "searchResults", "hits"],
    ]
    for path in paths_to_try:
        node = data
        for key in path:
            if isinstance(node, dict):
                node = node.get(key)
            else:
                node = None
                break
        if node and isinstance(node, list):
            hits = node
            break

    if not hits:
        return []

    for item in hits:
        try:
            sku       = str(item.get("sku") or item.get("id", ""))
            title     = item.get("name", "") or item.get("title", "")
            brand     = item.get("brand") or infer_brand(title, category)

            # Image
            image_keys = item.get("image_keys", []) or item.get("images", [])
            image_key  = image_keys[0] if image_keys else item.get("image", "")
            image_url  = build_image_url(image_key)

            # Pricing
            price_info    = item.get("price", {}) or {}
            current_price = float(price_info.get("now", 0) or price_info.get("value", 0) or item.get("now", 0) or 0)
            orig_price    = float(price_info.get("was", current_price) or current_price)
            if not current_price:
                continue

            # Rating
            rating       = float(item.get("average_rating", 0) or item.get("rating", 0) or 0) or None
            review_count = int(item.get("reviews_count", 0) or item.get("num_ratings", 0) or 0)

            # URL
            slug = (
                item.get("url") or
                item.get("slug") or
                item.get("product_url") or
                f"/product/{sku}/"
            )
            product_url = build_product_url(slug)

            # Express / availability
            is_available = bool(
                item.get("is_express_available") or
                item.get("is_fulfilled_by_noon") or
                item.get("is_available", True)
            )

            # Fulfilment type
            fulfilment = item.get("fulfilment_type", "") or ""

            items.append({
                "sku": sku,
                "title": title,
                "brand": brand,
                "product_url": product_url,
                "image_url": image_url,
                "current_price": current_price,
                "original_price": orig_price,
                "rating": rating,
                "review_count": review_count,
                "category": category,
                "is_available": is_available,
                "fulfilment": fulfilment,
            })

        except Exception as e:
            log.debug("    ✗ next_data item parse error: %s", e)

    return items


async def _scrape_dom(page, category: str) -> list[dict]:
    """DOM fallback: scrape product cards from rendered HTML."""
    items = []
    selectors = [
        "[data-qa='product-block']",
        ".productContainer",
        ".sc-bdnxRM",
        "[class*='productBlock']",
    ]

    cards = []
    for sel in selectors:
        found = await page.locator(sel).all()
        if found:
            cards = found
            break

    for card in cards:
        try:
            # Title
            title_el = card.locator(
                "[data-qa='product-name'], .productTitle, "
                "[class*='productName'], [class*='title']"
            )
            if not await title_el.count():
                continue
            title = (await title_el.first.inner_text()).strip()

            # Price
            price_el = card.locator(
                "[data-qa='price-now'], .priceNow, "
                "[class*='priceNow'], strong[class*='price']"
            )
            if not await price_el.count():
                continue
            current_price = parse_aed_price(await price_el.first.inner_text())
            if not current_price:
                continue

            # Original price
            orig_el = card.locator("[data-qa='price-was'], .priceWas, [class*='priceWas']")
            orig_price = None
            if await orig_el.count():
                orig_price = parse_aed_price(await orig_el.first.inner_text())

            # URL + SKU
            link_el = card.locator("a")
            href = await link_el.first.get_attribute("href") if await link_el.count() else ""
            product_url = build_product_url(href) if href else ""
            sku_m = re.search(r"/p/([A-Z0-9]+)/", href or "")
            sku = sku_m.group(1) if sku_m else href[-20:] if href else "unknown"

            # Image
            img_el = card.locator("img[src*='nooncdn'], img[data-src]")
            if not await img_el.count():
                img_el = card.locator("img")
            image_url = None
            if await img_el.count():
                image_url = (
                    await img_el.first.get_attribute("data-src") or
                    await img_el.first.get_attribute("src")
                )

            # Rating
            rating = None
            rating_el = card.locator("[class*='rating'], [data-qa='rating']")
            if await rating_el.count():
                rating_text = await rating_el.first.inner_text()
                m = re.search(r"([\d.]+)", rating_text)
                if m:
                    val = float(m.group(1))
                    if 0 < val <= 5:
                        rating = val

            items.append({
                "sku": sku,
                "title": title,
                "brand": infer_brand(title, category),
                "product_url": product_url,
                "image_url": image_url,
                "current_price": current_price,
                "original_price": orig_price or current_price,
                "rating": rating,
                "review_count": 0,
                "category": category,
                "is_available": True,
                "fulfilment": "",
            })

        except Exception as e:
            log.debug("    ✗ DOM card error: %s", e)

    return items


# ─── Detail page scraping ─────────────────────────────────────────────────────

@async_retry(max_attempts=2, backoff_base=4.0, exceptions=(PWTimeout, Exception))
async def scrape_product_detail(ctx, product_url: str, sku: str, category: str) -> dict:
    """
    Scrape a Noon product detail page.
    Extracts: seller info, full spec table, description, reviews, high-res images.
    Returns enrichment dict.
    """
    page = await ctx.new_page()
    enrichment = {}

    try:
        log.info("    detail → %s", product_url)
        await page.goto(product_url, wait_until="networkidle", timeout=45000)
        await accept_cookies(page)

        # Check for redirect/block
        current_url = page.url
        if "/404" in current_url or "not-found" in current_url:
            log.warning("    ✗ Product not found: %s", sku)
            return enrichment

        await human_delay(1.5, 3.0)
        await scroll_to_bottom(page, steps=5)
        await human_delay(0.5, 1.5)

        # ── Parse __NEXT_DATA__ for detailed product data ──────────────────────
        next_data_raw = await page.evaluate(
            "() => document.getElementById('__NEXT_DATA__')?.textContent"
        )
        product_json = {}
        if next_data_raw:
            try:
                nd = json.loads(next_data_raw)
                # Navigate to product data
                product_json = (
                    nd.get("props", {}).get("pageProps", {}).get("product", {}) or
                    nd.get("props", {}).get("pageProps", {}).get("initialData", {}).get("product", {}) or
                    nd.get("props", {}).get("pageProps", {}).get("item", {}) or
                    {}
                )
            except json.JSONDecodeError:
                pass

        # ── Title ──────────────────────────────────────────────────────────────
        if product_json.get("name"):
            enrichment["title_full"] = product_json["name"]
        else:
            title_el = page.locator("h1[data-qa='pdp-product-name'], .productTitle h1, h1.sc-dkrFOg")
            if await title_el.count():
                enrichment["title_full"] = (await title_el.first.inner_text()).strip()

        # ── Brand ──────────────────────────────────────────────────────────────
        brand = (
            product_json.get("brand") or
            product_json.get("brand_name")
        )
        if not brand:
            brand_el = page.locator("[data-qa='pdp-brand-name'], .brandName, a[href*='/brand/']")
            if await brand_el.count():
                brand = (await brand_el.first.inner_text()).strip()
        if brand:
            enrichment["brand"] = brand[:50]

        # ── Seller / seller info ───────────────────────────────────────────────
        seller_name = product_json.get("seller_name") or product_json.get("sold_by")
        if not seller_name:
            seller_el = page.locator(
                "[data-qa='pdp-seller-name'], .sellerName, "
                "[class*='sellerName'], [data-testid='seller-name']"
            )
            if await seller_el.count():
                seller_name = (await seller_el.first.inner_text()).strip()

        if seller_name:
            # Clean "Sold by X" prefix
            seller_name = re.sub(r"^(Sold by|Seller:|by)\s+", "", seller_name, flags=re.IGNORECASE).strip()
            enrichment["seller_name"] = seller_name[:100]

        # Seller rating
        seller_rating_raw = product_json.get("seller_rating") or product_json.get("vendor_rating")
        if seller_rating_raw:
            try:
                enrichment["seller_rating"] = float(seller_rating_raw)
            except (ValueError, TypeError):
                pass
        else:
            sr_el = page.locator("[data-qa='seller-rating'], [class*='sellerRating']")
            if await sr_el.count():
                sr_text = await sr_el.first.inner_text()
                m = re.search(r"([\d.]+)", sr_text)
                if m:
                    enrichment["seller_rating"] = float(m.group(1))

        # Fulfilment
        if product_json.get("is_fulfilled_by_noon") or product_json.get("is_express_available"):
            enrichment["fulfilment"] = "FBN"  # Fulfilled By Noon

        # ── Pricing ────────────────────────────────────────────────────────────
        price_info = product_json.get("price", {}) or {}
        if price_info.get("now"):
            enrichment["current_price"] = float(price_info["now"])
        if price_info.get("was") and float(price_info["was"]) > 0:
            enrichment["original_price"] = float(price_info["was"])

        # DOM fallback for price
        if "current_price" not in enrichment:
            price_selectors = [
                "[data-qa='price-now'] strong",
                ".priceNow strong",
                "[class*='priceNow']",
                "strong[class*='amount']",
            ]
            for sel in price_selectors:
                el = page.locator(sel)
                if await el.count():
                    p = parse_aed_price(await el.first.inner_text())
                    if p:
                        enrichment["current_price"] = p
                        break

        # ── Ratings ────────────────────────────────────────────────────────────
        avg_rating = (
            product_json.get("average_rating") or
            product_json.get("rating")
        )
        if avg_rating:
            try:
                enrichment["rating"] = float(avg_rating)
            except (ValueError, TypeError):
                pass

        review_count = (
            product_json.get("reviews_count") or
            product_json.get("num_ratings") or
            product_json.get("ratings_count")
        )
        if review_count:
            enrichment["review_count"] = int(review_count)

        # DOM fallback
        if "rating" not in enrichment:
            rating_el = page.locator(
                "[data-qa='pdp-rating'], .averageRating, "
                "span[class*='averageRating']"
            )
            if await rating_el.count():
                m = re.search(r"([\d.]+)", await rating_el.first.inner_text())
                if m:
                    enrichment["rating"] = float(m.group(1))

        # Reviews text
        reviews_el = page.locator("[data-qa='pdp-review-count'], [class*='reviewCount']")
        if await reviews_el.count() and "review_count" not in enrichment:
            m = re.search(r"([\d,]+)", await reviews_el.first.inner_text())
            if m:
                enrichment["review_count"] = int(m.group().replace(",", ""))

        # ── Product specifications table ───────────────────────────────────────
        tech_specs = {}

        # From JSON
        spec_list = (
            product_json.get("specifications") or
            product_json.get("attributes") or
            product_json.get("specs") or
            []
        )
        if isinstance(spec_list, list):
            for spec_item in spec_list:
                if isinstance(spec_item, dict):
                    key = spec_item.get("key") or spec_item.get("name") or spec_item.get("label", "")
                    val = spec_item.get("value") or spec_item.get("val", "")
                    if key and val:
                        tech_specs[key] = str(val)
        elif isinstance(spec_list, dict):
            for key, val in spec_list.items():
                if key and val:
                    tech_specs[key] = str(val)

        # From DOM spec table
        if not tech_specs:
            spec_row_els = await page.locator(
                "[data-qa='pdp-specs-table'] tr, "
                ".specifications tr, "
                ".productSpecs tr, "
                "[class*='specRow'], "
                "[class*='specItem']"
            ).all()
            for row in spec_row_els:
                try:
                    cells = await row.locator("td, th, span, div").all()
                    if len(cells) >= 2:
                        key = (await cells[0].inner_text()).strip()
                        val = (await cells[1].inner_text()).strip()
                        if key and val and len(key) < 60:
                            tech_specs[key] = val
                except Exception:
                    pass

        if tech_specs:
            enrichment["tech_specs_raw"] = tech_specs

        # ── Description ────────────────────────────────────────────────────────
        desc = product_json.get("description") or product_json.get("long_description", "")
        if not desc:
            desc_el = page.locator(
                "[data-qa='pdp-description'], .productDescription, "
                "[class*='productDescription'], [class*='description']"
            )
            if await desc_el.count():
                desc = (await desc_el.first.inner_text()).strip()[:3000]
        if desc:
            enrichment["description"] = str(desc)[:3000]

        # ── Feature highlights ─────────────────────────────────────────────────
        bullets = []
        highlight_els = await page.locator(
            "[data-qa='pdp-highlights'] li, "
            ".productHighlights li, "
            "[class*='highlight'] li"
        ).all()
        for el in highlight_els:
            text = (await el.inner_text()).strip()
            if text and len(text) > 4:
                bullets.append(text)
        if bullets:
            enrichment["feature_bullets"] = bullets[:15]

        # ── High-res image ─────────────────────────────────────────────────────
        images = product_json.get("image_keys", []) or product_json.get("images", [])
        if images:
            enrichment["image_url"] = build_image_url(images[0])
        else:
            img_el = page.locator(
                "[data-qa='pdp-product-image'] img, "
                ".productImage img, "
                "[class*='productImage'] img"
            )
            if await img_el.count():
                src = (
                    await img_el.first.get_attribute("data-src") or
                    await img_el.first.get_attribute("src")
                )
                if src:
                    enrichment["image_url"] = src

        # ── Parse specs ────────────────────────────────────────────────────────
        full_title = enrichment.get("title_full", "")
        description = enrichment.get("description", "")
        bullets_text = " ".join(enrichment.get("feature_bullets", []))
        combined = f"{full_title} {description} {bullets_text}"

        parsed_specs = parse_specs(category, full_title, combined, tech_specs or None)
        if parsed_specs:
            enrichment["specs"] = parsed_specs

        log.info("    ✓ SKU %s — seller=%s, specs_keys=%d",
                 sku,
                 enrichment.get("seller_name", "?"),
                 len(enrichment.get("specs", {})))

    except PWTimeout:
        log.warning("    ✗ Detail page timeout for SKU %s", sku)
    except Exception as e:
        log.error("    ✗ Detail page error for SKU %s: %s", sku, e)
    finally:
        await page.close()

    return enrichment


# ─── Full scrape pipeline ─────────────────────────────────────────────────────

async def scrape_query(ctx, query: str, category: str) -> list[dict]:
    """
    Full pipeline for one search query:
    1. Scrape search result pages → collect SKUs + basic data
    2. Fetch detail page for each unique SKU → enrich with full specs
    Returns list of product dicts ready for upsert.
    """
    # Phase 1: Search results
    search_results = []
    seen_skus = set()

    for page_num in range(1, MAX_SEARCH_PAGES + 1):
        items = await scrape_search_page(ctx, query, category, page_num)
        if not items:
            break
        for item in items:
            if item["sku"] not in seen_skus:
                seen_skus.add(item["sku"])
                search_results.append(item)
        if page_num < MAX_SEARCH_PAGES:
            await human_delay(4, 9)

    log.info("  Phase 1: %d unique products from search for '%s'", len(search_results), query)

    # Phase 2: Detail pages — limit per query
    max_per_query = max(5, 120 // len(SEARCH_TARGETS))
    to_enrich = search_results[:max_per_query]

    products = []
    for i, item in enumerate(to_enrich):
        enrichment = await scrape_product_detail(ctx, item["product_url"], item["sku"], category)
        await human_delay(3.0, 7.0)

        product = _build_product_record(item, enrichment, category)
        products.append(product)

        if (i + 1) % 5 == 0:
            log.info("  Progress: %d/%d detail pages", i + 1, len(to_enrich))

    return products


def _build_product_record(search_item: dict, enrichment: dict, category: str) -> dict:
    """Merge search data with detail enrichment into DB-ready dict."""
    sku = search_item["sku"]
    title = enrichment.get("title_full") or search_item["title"]
    brand = enrichment.get("brand") or search_item.get("brand") or infer_brand(title, category)

    current_price  = enrichment.get("current_price") or search_item["current_price"]
    original_price = enrichment.get("original_price") or search_item.get("original_price") or current_price

    specs = enrichment.get("specs", {})
    if not specs:
        specs = parse_specs(category, title)

    tags = infer_tags(category, specs, title)
    if search_item.get("fulfilment") == "FBN":
        tags.append("Fulfilled by Noon")

    product_url   = search_item["product_url"]
    affiliate_url = make_affiliate_url(product_url)

    return {
        "category":       category,
        "brand":          brand or "Unknown",
        "model":          title[:250],
        "retailer":       "noon",
        "retailer_id":    sku,
        "product_url":    product_url,
        "affiliate_url":  affiliate_url,
        "image_url":      enrichment.get("image_url") or search_item.get("image_url"),
        "current_price":  current_price,
        "original_price": original_price,
        "specs":          specs,
        "tags":           tags,
        "seller_name":    enrichment.get("seller_name"),
        "seller_rating":  enrichment.get("seller_rating"),
        "rating":         enrichment.get("rating") or search_item.get("rating"),
        "review_count":   enrichment.get("review_count") or search_item.get("review_count", 0),
        "is_available":   search_item.get("is_available", True),
        "feature_bullets": enrichment.get("feature_bullets"),
        "tech_specs_raw":  enrichment.get("tech_specs_raw"),
    }


# ─── Entry point ─────────────────────────────────────────────────────────────

async def main():
    log.info("=== GulfDeals Noon.ae Scraper ===")
    all_products = []

    async with async_playwright() as pw:
        browser, ctx = await make_browser(pw)
        try:
            for i, target in enumerate(SEARCH_TARGETS):
                log.info("\n[%d/%d] [%s] Query: '%s'",
                         i + 1, len(SEARCH_TARGETS),
                         target["category"].upper(),
                         target["query"])
                products = await scrape_query(ctx, target["query"], target["category"])
                all_products.extend(products)
                log.info("  → Collected %d products so far", len(all_products))

                if i < len(SEARCH_TARGETS) - 1:
                    await human_delay(8, 18)

        except Exception as e:
            log.error("Fatal scraper error: %s", e)
        finally:
            await ctx.close()
            await browser.close()

    # Deduplicate by SKU
    seen, unique = {}, []
    for p in all_products:
        key = p["retailer_id"]
        if key not in seen:
            seen[key] = p
            unique.append(p)
        else:
            # Prefer richer spec entry
            if len(p.get("specs", {})) > len(seen[key].get("specs", {})):
                idx = unique.index(seen[key])
                unique[idx] = p
                seen[key] = p

    log.info("\n=== Upserting %d unique products to Supabase ===", len(unique))
    success, failed = bulk_upsert_products(unique)
    log.info("✓ Done. %d upserted, %d failed.", success, failed)


if __name__ == "__main__":
    asyncio.run(main())
