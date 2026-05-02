"""
GulfDeals — Amazon.ae scraper
Scrapes gaming laptops, CPUs, and GPUs from Amazon.ae.

Strategy:
  1. Search results pages → collect ASINs + basic pricing
  2. Product detail pages → extract full specs, seller info, reviews

IMPORTANT: Amazon actively blocks scrapers. Production requirements:
  - Residential rotating proxies (BrightData / Oxylabs) — set PROXY_HOST env var
  - Random delays between all requests
  - Realistic browser fingerprint via Playwright stealth mode
  - Respect robots.txt and Amazon ToS — consider PA API for production scale

Usage:
    cd project/backend/scrapers
    python amazon_ae.py
"""

import asyncio, re, json, sys, os
from typing import Optional
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# Allow running from scrapers/ directory directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base import (
    make_browser, human_delay, micro_delay, scroll_to_bottom,
    bulk_upsert_products, log, async_retry, parse_aed_price,
)
from spec_parser import parse_specs, infer_tags

BASE_URL = "https://www.amazon.ae"
AFFILIATE_TAG = "gulfdeals-21"   # Replace with your Amazon Associates tag

# Comprehensive search targets — covers all major gaming product categories
SEARCH_TARGETS = [
    # Laptops
    {"query": "gaming laptop",                    "category": "laptop"},
    {"query": "ASUS ROG gaming laptop",           "category": "laptop"},
    {"query": "MSI gaming laptop",                "category": "laptop"},
    {"query": "Lenovo Legion gaming laptop",      "category": "laptop"},
    {"query": "Razer Blade gaming laptop",        "category": "laptop"},
    # CPUs — Intel
    {"query": "Intel Core i9 14th gen processor", "category": "cpu"},
    {"query": "Intel Core i7 14th gen processor", "category": "cpu"},
    {"query": "Intel Core i5 14th gen processor", "category": "cpu"},
    # CPUs — AMD
    {"query": "AMD Ryzen 9 7000 processor",       "category": "cpu"},
    {"query": "AMD Ryzen 7 7800X3D processor",    "category": "cpu"},
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

# Max search result pages per query (3 × ~20 items = ~60 products per query)
MAX_SEARCH_PAGES = 3
# Max detail pages to fetch per run (respect rate limits)
MAX_DETAIL_PAGES_PER_RUN = 120


def make_affiliate_url(asin: str) -> str:
    return f"{BASE_URL}/dp/{asin}?tag={AFFILIATE_TAG}"


def clean_price_text(text: str) -> Optional[float]:
    """Extract numeric price from Amazon price strings."""
    if not text:
        return None
    # Amazon splits price into whole + fraction parts
    cleaned = text.replace(",", "").replace("\xa0", "").strip()
    # Remove currency symbols
    cleaned = re.sub(r"[^\d.]", " ", cleaned).strip()
    parts = cleaned.split()
    if parts:
        try:
            return float(parts[0])
        except ValueError:
            return None
    return None


# ─── Search result scraping ───────────────────────────────────────────────────

@async_retry(max_attempts=2, backoff_base=3.0, exceptions=(PWTimeout, Exception))
async def scrape_search_page(ctx, query: str, category: str, page_num: int = 1) -> list[dict]:
    """
    Scrape one page of Amazon.ae search results.
    Returns list of dicts with ASIN, title, pricing, rating, image.
    """
    url = f"{BASE_URL}/s?k={query.replace(' ', '+')}&page={page_num}"
    page = await ctx.new_page()
    items = []

    try:
        log.info("  GET %s", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=35000)

        # Block detection
        if await page.locator("form[action='/errors/validateCaptcha']").count() > 0:
            log.warning("  ✗ CAPTCHA on search page — skipping (rotate proxy)")
            return []

        page_title = await page.title()
        if "robot check" in page_title.lower() or "sorry" in page_title.lower():
            log.warning("  ✗ Bot detection page — skipping")
            return []

        await human_delay(1.5, 3.5)
        await scroll_to_bottom(page, steps=3)

        # Product cards
        cards = await page.locator("div[data-component-type='s-search-result']").all()
        log.info("  Found %d product cards on page %d", len(cards), page_num)

        for card in cards:
            try:
                # ASIN
                asin = await card.get_attribute("data-asin")
                if not asin:
                    continue

                # Sponsored? Flag but still include
                is_sponsored = await card.locator(".s-label-popover-default").count() > 0

                # Title
                title_el = card.locator("h2 a span")
                if not await title_el.count():
                    continue
                title = (await title_el.first.inner_text()).strip()

                # Product URL
                link_el = card.locator("h2 a")
                href = await link_el.first.get_attribute("href") or ""
                product_url = BASE_URL + href if href.startswith("/") else href
                # Strip query params for clean URL, keep ASIN path
                product_url = re.sub(r"\?.*", "", product_url)

                # Current price — Amazon splits into whole.fraction
                price_whole = ""
                price_frac = ""
                whole_el = card.locator(".a-price-whole")
                frac_el = card.locator(".a-price-fraction")
                if await whole_el.count():
                    price_whole = (await whole_el.first.inner_text()).replace(",", "").replace(".", "").strip()
                if await frac_el.count():
                    price_frac = (await frac_el.first.inner_text()).strip()

                current_price = None
                if price_whole:
                    try:
                        current_price = float(f"{price_whole}.{price_frac}" if price_frac else price_whole)
                    except ValueError:
                        pass

                if not current_price:
                    # Fallback: try offscreen price text
                    offscreen_el = card.locator(".a-price .a-offscreen")
                    if await offscreen_el.count():
                        current_price = parse_aed_price(await offscreen_el.first.inner_text())

                if not current_price:
                    continue  # Skip if no price

                # Original (was) price
                orig_el = card.locator(".a-price.a-text-price .a-offscreen")
                original_price = None
                if await orig_el.count():
                    original_price = parse_aed_price(await orig_el.first.inner_text())

                # Rating
                rating = None
                rating_el = card.locator("span[aria-label*='out of 5 stars']")
                if await rating_el.count():
                    rating_text = await rating_el.first.get_attribute("aria-label") or ""
                    m = re.search(r"([\d.]+)\s+out\s+of\s+5", rating_text)
                    if m:
                        rating = float(m.group(1))

                # Review count
                review_count = 0
                review_el = card.locator("span[aria-label*='ratings'], span[aria-label*='reviews']")
                if not await review_el.count():
                    review_el = card.locator(".s-underline-link-text")
                if await review_el.count():
                    review_text = await review_el.first.get_attribute("aria-label") or await review_el.first.inner_text()
                    m = re.search(r"([\d,]+)", review_text)
                    if m:
                        review_count = int(m.group().replace(",", ""))

                # Image
                img_el = card.locator("img.s-image")
                image_url = await img_el.first.get_attribute("src") if await img_el.count() else None

                # Badge (e.g. "#1 Best Seller", "Amazon's Choice")
                badge = None
                badge_el = card.locator(".s-label-popover-default, .a-badge-text")
                if await badge_el.count():
                    badge = (await badge_el.first.inner_text()).strip()

                items.append({
                    "asin": asin,
                    "title": title,
                    "product_url": product_url,
                    "current_price": current_price,
                    "original_price": original_price or current_price,
                    "rating": rating,
                    "review_count": review_count,
                    "image_url": image_url,
                    "badge": badge,
                    "category": category,
                    "is_sponsored": is_sponsored,
                })

            except Exception as e:
                log.debug("  ✗ Card parse error: %s", e)

    except PWTimeout:
        log.warning("  ✗ Search page timeout for query '%s' page %d", query, page_num)
    finally:
        await page.close()

    return items


# ─── Detail page scraping ─────────────────────────────────────────────────────

@async_retry(max_attempts=2, backoff_base=4.0, exceptions=(PWTimeout, Exception))
async def scrape_product_detail(ctx, asin: str, category: str) -> dict:
    """
    Scrape a full Amazon.ae product detail page.
    Extracts: seller info, full specs table, feature bullets, description.
    Returns enrichment dict to merge with search result data.
    """
    url = f"{BASE_URL}/dp/{asin}"
    page = await ctx.new_page()
    enrichment = {}

    try:
        log.info("    detail → %s", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)

        # Bot check
        if await page.locator("form[action='/errors/validateCaptcha']").count() > 0:
            log.warning("    ✗ CAPTCHA on detail page for ASIN %s", asin)
            return enrichment

        await human_delay(1.5, 3.0)
        await scroll_to_bottom(page, steps=4)
        await human_delay(0.5, 1.5)

        # ── Title (authoritative version) ────────────────────────────────────
        title_el = page.locator("#productTitle")
        if await title_el.count():
            enrichment["title_full"] = (await title_el.inner_text()).strip()

        # ── Seller information ────────────────────────────────────────────────
        seller_name = None

        # "Sold by X" text
        sold_by_el = page.locator("#merchant-info, #sellerProfileTriggerId, #tabular-buybox-seller-name a")
        if await sold_by_el.count():
            seller_name = (await sold_by_el.first.inner_text()).strip()
            seller_name = re.sub(r"^Sold by\s+", "", seller_name, flags=re.IGNORECASE).strip()

        # Fallback: "Ships from and sold by" section
        if not seller_name:
            ships_el = page.locator("#tabular-buybox-container")
            if await ships_el.count():
                ships_text = await ships_el.inner_text()
                m = re.search(r"Sold by\s+(.+?)(?:\n|$)", ships_text)
                if m:
                    seller_name = m.group(1).strip()

        if seller_name:
            enrichment["seller_name"] = seller_name[:100]

        # Seller rating — appears as "X% positive in the last 12 months"
        seller_rating = None
        rating_el = page.locator("#sellerProfileTriggerId")
        if await rating_el.count():
            parent_text = await page.locator("#merchant-info").inner_text() if await page.locator("#merchant-info").count() else ""
            m = re.search(r"([\d.]+)%\s*positive", parent_text)
            if m:
                seller_rating = float(m.group(1))

        if seller_rating:
            enrichment["seller_rating"] = seller_rating

        # ── Current price (detail page is authoritative) ──────────────────────
        price_selectors = [
            "#corePriceDisplay_desktop_feature_div .a-price-whole",
            ".a-price .a-price-whole",
            "#price_inside_buybox",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            ".priceToPay .a-price-whole",
        ]
        for sel in price_selectors:
            el = page.locator(sel)
            if await el.count():
                whole_text = (await el.first.inner_text()).replace(",", "").replace(".", "").strip()
                frac_el = page.locator(sel.replace("whole", "fraction"))
                frac_text = (await frac_el.first.inner_text()).strip() if await frac_el.count() else "00"
                try:
                    enrichment["current_price"] = float(f"{whole_text}.{frac_text}")
                    break
                except ValueError:
                    pass

        # Original (was) price
        orig_selectors = [
            "#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen",
            ".a-price.a-text-price .a-offscreen",
            "#listPrice",
            ".priceBlockStrikePriceString",
        ]
        for sel in orig_selectors:
            el = page.locator(sel)
            if await el.count():
                price = parse_aed_price(await el.first.inner_text())
                if price:
                    enrichment["original_price"] = price
                    break

        # Savings badge
        savings_el = page.locator(".savingsPercentage, .a-badge-text:has-text('%')")
        if await savings_el.count():
            savings_text = await savings_el.first.inner_text()
            m = re.search(r"(\d+)%", savings_text)
            if m:
                enrichment["listed_discount_pct"] = int(m.group(1))

        # ── Ratings & reviews ─────────────────────────────────────────────────
        rating_el = page.locator("#acrPopover, #averageCustomerReviews")
        if await rating_el.count():
            rating_title = await rating_el.first.get_attribute("title") or ""
            m = re.search(r"([\d.]+)\s+out\s+of\s+5", rating_title)
            if m:
                enrichment["rating"] = float(m.group(1))

        reviews_el = page.locator("#acrCustomerReviewText, #acrCustomerReviewLink span")
        if await reviews_el.count():
            review_text = await reviews_el.first.inner_text()
            m = re.search(r"([\d,]+)", review_text)
            if m:
                enrichment["review_count"] = int(m.group().replace(",", ""))

        # Rating breakdown
        rating_breakdown = {}
        for stars in range(1, 6):
            bar_el = page.locator(f'[title="{stars} star"] + td .a-size-small')
            if await bar_el.count():
                pct_text = await bar_el.first.inner_text()
                m = re.search(r"(\d+)%", pct_text)
                if m:
                    rating_breakdown[f"{stars}_star_pct"] = int(m.group(1))
        if rating_breakdown:
            enrichment["rating_breakdown"] = rating_breakdown

        # ── Feature bullets ────────────────────────────────────────────────────
        bullets = []
        bullet_els = await page.locator("#feature-bullets ul li span.a-list-item").all()
        for el in bullet_els:
            text = (await el.inner_text()).strip()
            if text and len(text) > 5:
                bullets.append(text)
        if bullets:
            enrichment["feature_bullets"] = bullets[:15]  # Cap at 15 bullets

        # ── Technical specifications table ─────────────────────────────────────
        tech_specs = {}

        # Method 1: #productDetails_techSpec_section_1 (table format)
        spec_rows = await page.locator(
            "#productDetails_techSpec_section_1 tr, "
            "#productDetails_detailBullets_sections1 tr, "
            "#detailBullets_feature_div li"
        ).all()

        for row in spec_rows:
            try:
                # Try table row format
                th_el = row.locator("th")
                td_el = row.locator("td")
                if await th_el.count() and await td_el.count():
                    key = (await th_el.first.inner_text()).strip()
                    val = (await td_el.first.inner_text()).strip()
                    if key and val:
                        tech_specs[key] = val
                else:
                    # Try detail bullet format (key : value)
                    text = (await row.inner_text()).strip()
                    if ":" in text:
                        parts = text.split(":", 1)
                        if len(parts) == 2:
                            tech_specs[parts[0].strip()] = parts[1].strip()
            except Exception:
                pass

        # Method 2: #aplus section for brand's enhanced content (A+ content)
        aplus_el = page.locator("#aplus, #dpx-aplus-product-description_feature_div")
        aplus_text = ""
        if await aplus_el.count():
            aplus_text = await aplus_el.first.inner_text()

        # Method 3: Technical Details accordion
        tech_detail_rows = await page.locator(
            "#technicalSpecifications_section_1 tr, "
            "#prodDetails tr"
        ).all()
        for row in tech_detail_rows:
            try:
                cells = await row.locator("td, th").all()
                if len(cells) >= 2:
                    key = (await cells[0].inner_text()).strip()
                    val = (await cells[1].inner_text()).strip()
                    if key and val and key not in tech_specs:
                        tech_specs[key] = val
            except Exception:
                pass

        if tech_specs:
            enrichment["tech_specs_raw"] = tech_specs

        # ── Product description ────────────────────────────────────────────────
        desc_el = page.locator("#productDescription p, #productDescription span")
        description = ""
        if await desc_el.count():
            desc_parts = []
            for el in (await desc_el.all())[:5]:
                text = (await el.inner_text()).strip()
                if text:
                    desc_parts.append(text)
            description = " ".join(desc_parts)[:2000]
            enrichment["description"] = description

        # ── High-res image ────────────────────────────────────────────────────
        img_el = page.locator("#imgBlkFront, #landingImage, #main-image")
        if await img_el.count():
            # Try data-old-hires or data-a-hires for full-res image
            hires = (
                await img_el.first.get_attribute("data-old-hires") or
                await img_el.first.get_attribute("data-a-hires") or
                await img_el.first.get_attribute("src")
            )
            if hires:
                enrichment["image_url"] = hires

        # ── Brand from byline ──────────────────────────────────────────────────
        brand_el = page.locator("#bylineInfo a, #brand")
        if await brand_el.count():
            brand_text = (await brand_el.first.inner_text()).strip()
            brand_text = re.sub(r"^(Visit the|Brand:|by)\s+", "", brand_text, flags=re.IGNORECASE)
            brand_text = re.sub(r"\s+Store$", "", brand_text, flags=re.IGNORECASE)
            if brand_text:
                enrichment["brand"] = brand_text[:50]

        # ── Parse specs using spec_parser ──────────────────────────────────────
        full_title = enrichment.get("title_full", "")
        bullets_text = " ".join(enrichment.get("feature_bullets", []))
        combined_text = f"{full_title} {description} {bullets_text} {aplus_text}"

        parsed_specs = parse_specs(category, full_title, combined_text, tech_specs)
        if parsed_specs:
            enrichment["specs"] = parsed_specs

        log.info("    ✓ ASIN %s — seller=%s, specs_keys=%d",
                 asin,
                 enrichment.get("seller_name", "?"),
                 len(enrichment.get("specs", {})))

    except PWTimeout:
        log.warning("    ✗ Detail page timeout for ASIN %s", asin)
    except Exception as e:
        log.error("    ✗ Detail page error for ASIN %s: %s", asin, e)
    finally:
        await page.close()

    return enrichment


# ─── Full scrape pipeline ─────────────────────────────────────────────────────

async def scrape_query(ctx, query: str, category: str) -> list[dict]:
    """
    Full pipeline for one search query:
    1. Scrape search results pages → collect ASINs + basic data
    2. Fetch detail page for each unique ASIN → enrich with full specs
    Returns list of product dicts ready for upsert.
    """
    # Phase 1: Collect from search results
    search_results = []
    seen_asins = set()

    for page_num in range(1, MAX_SEARCH_PAGES + 1):
        items = await scrape_search_page(ctx, query, category, page_num)
        if not items:
            break

        for item in items:
            if item["asin"] not in seen_asins:
                seen_asins.add(item["asin"])
                search_results.append(item)

        if page_num < MAX_SEARCH_PAGES:
            await human_delay(4, 9)

    log.info("  Phase 1 complete: %d unique products from search for '%s'", len(search_results), query)

    # Phase 2: Enrich with detail pages
    # Limit to avoid too many requests per query
    to_enrich = search_results[:MAX_DETAIL_PAGES_PER_RUN // len(SEARCH_TARGETS) + 3]

    products = []
    for i, item in enumerate(to_enrich):
        asin = item["asin"]
        category = item["category"]

        enrichment = await scrape_product_detail(ctx, asin, category)
        await human_delay(3.0, 7.0)  # Respect rate limits between detail page calls

        # Merge search result with detail enrichment
        product = build_product_record(item, enrichment)
        products.append(product)

        if (i + 1) % 5 == 0:
            log.info("  Progress: %d/%d detail pages fetched", i + 1, len(to_enrich))

    return products


def build_product_record(search_item: dict, enrichment: dict) -> dict:
    """Merge search result data with detail page enrichment into a DB-ready dict."""
    asin = search_item["asin"]
    category = search_item["category"]

    # Title — prefer full title from detail page
    title = enrichment.get("title_full") or search_item["title"]

    # Brand extraction
    brand = enrichment.get("brand", "")
    if not brand:
        brand = _infer_brand(title, category)

    # Price — detail page is more reliable
    current_price = enrichment.get("current_price") or search_item["current_price"]
    original_price = enrichment.get("original_price") or search_item.get("original_price") or current_price

    # Specs
    specs = enrichment.get("specs", {})
    if not specs:
        # Fallback: parse from title only (no description)
        specs = parse_specs(category, title)

    # Tags
    tags = infer_tags(category, specs, title)
    if search_item.get("badge"):
        tags.append(search_item["badge"])

    return {
        "category":       category,
        "brand":          brand or "Unknown",
        "model":          title[:250],
        "retailer":       "amazon_ae",
        "retailer_id":    asin,
        "product_url":    f"{BASE_URL}/dp/{asin}",
        "affiliate_url":  make_affiliate_url(asin),
        "image_url":      enrichment.get("image_url") or search_item.get("image_url"),
        "current_price":  current_price,
        "original_price": original_price,
        "specs":          specs,
        "tags":           tags,
        "seller_name":    enrichment.get("seller_name"),
        "seller_rating":  enrichment.get("seller_rating"),
        "rating":         enrichment.get("rating") or search_item.get("rating"),
        "review_count":   enrichment.get("review_count") or search_item.get("review_count", 0),
        "is_available":   True,
        "feature_bullets": enrichment.get("feature_bullets"),
        "tech_specs_raw": enrichment.get("tech_specs_raw"),
    }


def _infer_brand(title: str, category: str) -> str:
    """Infer brand from product title."""
    brands = {
        "laptop": ["ASUS", "MSI", "Lenovo", "Acer", "HP", "Razer", "Dell",
                   "Gigabyte", "Samsung", "LG", "Huawei", "Honor"],
        "cpu":    ["Intel", "AMD"],
        "gpu":    ["ASUS", "MSI", "Gigabyte", "EVGA", "Sapphire", "PowerColor",
                   "Zotac", "XFX", "PNY", "Colorful", "Gainward", "Palit",
                   "Inno3D", "NVIDIA", "AMD"],
    }
    title_lower = title.lower()
    for brand in brands.get(category, []):
        if brand.lower() in title_lower:
            return brand
    # Fallback: first word of title
    words = title.split()
    return words[0] if words else "Unknown"


# ─── Entry point ─────────────────────────────────────────────────────────────

async def main():
    log.info("=== GulfDeals Amazon.ae Scraper ===")
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

                # Longer pause between different query groups
                if i < len(SEARCH_TARGETS) - 1:
                    await human_delay(8, 18)

        except Exception as e:
            log.error("Fatal scraper error: %s", e)
        finally:
            await ctx.close()
            await browser.close()

    # Deduplicate by ASIN (keep highest-quality entry)
    seen, unique = {}, []
    for p in all_products:
        key = p["retailer_id"]
        if key not in seen:
            seen[key] = p
            unique.append(p)
        else:
            # Prefer entry with more specs
            if len(p.get("specs", {})) > len(seen[key].get("specs", {})):
                idx = unique.index(seen[key])
                unique[idx] = p
                seen[key] = p

    log.info("\n=== Upserting %d unique products to Supabase ===", len(unique))
    success, failed = bulk_upsert_products(unique)
    log.info("✓ Done. %d upserted, %d failed.", success, failed)


if __name__ == "__main__":
    asyncio.run(main())
