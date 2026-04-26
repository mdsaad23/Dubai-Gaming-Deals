"""
GulfDeals — Shared scraper base
Handles: Playwright browser setup, proxy rotation, Supabase upsert
"""

import os, asyncio, random
from datetime import datetime
from supabase import create_client, Client
from playwright.async_api import async_playwright, BrowserContext

SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_SERVICE_KEY"]   # service role — never expose
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Proxy config (BrightData / Oxylabs residential) ─────────────────────────
PROXY = {
    "server":   f"http://{os.environ.get('PROXY_HOST', '')}:{os.environ.get('PROXY_PORT', 22225)}",
    "username": os.environ.get("PROXY_USER", ""),
    "password": os.environ.get("PROXY_PASS", ""),
} if os.environ.get("PROXY_HOST") else None   # None = direct connection (dev only)

# Realistic desktop UA pool
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


async def make_browser(playwright) -> tuple:
    """Launch a stealth Chromium browser with optional proxy."""
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    ctx: BrowserContext = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1440, "height": 900},
        locale="en-AE",
        timezone_id="Asia/Dubai",
        proxy=PROXY,
        extra_http_headers={
            "Accept-Language": "en-AE,en;q=0.9,ar;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        },
    )
    # Mask headless signals
    await ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)
    return browser, ctx


async def human_delay(min_s=2.5, max_s=6.0):
    """Random pause to mimic human browsing speed."""
    await asyncio.sleep(random.uniform(min_s, max_s))


def upsert_product(data: dict) -> str:
    """
    Upsert product into Supabase. Returns the product id.
    Unique constraint on (retailer, retailer_id) handles deduplication.
    Price history is appended automatically via DB trigger.
    """
    data["last_scraped"] = datetime.utcnow().isoformat()
    res = (
        supabase.table("products")
        .upsert(data, on_conflict="retailer,retailer_id")
        .execute()
    )
    return res.data[0]["id"]
