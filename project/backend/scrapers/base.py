"""
GulfDeals — Shared scraper base
Handles: Playwright browser setup, proxy rotation, Supabase upsert, logging, retry
"""

import os, asyncio, random, logging, functools, time
from datetime import datetime, timezone
from typing import Optional, Callable, Any
from supabase import create_client, Client
from playwright.async_api import async_playwright, BrowserContext

# ─── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("gulfdeals")


# ─── Supabase client ─────────────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]   # service role — never expose client-side
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ─── Proxy config (BrightData / Oxylabs residential) ─────────────────────────
PROXY = {
    "server":   f"http://{os.environ.get('PROXY_HOST', '')}:{os.environ.get('PROXY_PORT', 22225)}",
    "username": os.environ.get("PROXY_USER", ""),
    "password": os.environ.get("PROXY_PASS", ""),
} if os.environ.get("PROXY_HOST") else None   # None = direct connection (dev mode only)


# ─── Realistic UA pool — Chrome/Firefox/Safari on Win/Mac ────────────────────
USER_AGENTS = [
    # Chrome 124 Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome 124 Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Edge 124 Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Firefox 125 Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari 17.4 Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Chrome 124 on recent Mac M1
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 2560, "height": 1440},
]


# ─── Browser factory ─────────────────────────────────────────────────────────

async def make_browser(playwright) -> tuple:
    """Launch a stealth Chromium browser with optional residential proxy."""
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--disable-gpu",
        ],
    )
    ctx: BrowserContext = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport=random.choice(VIEWPORTS),
        locale="en-AE",
        timezone_id="Asia/Dubai",
        proxy=PROXY,
        extra_http_headers={
            "Accept-Language": "en-AE,en;q=0.9,ar;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    # Mask headless / automation signals
    await ctx.add_init_script("""
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        // Fake chrome runtime
        window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {}, app: {} };
        // Fake plugins (real browsers have plugins)
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        // Fake languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-AE', 'en', 'ar']
        });
        // Remove automation in permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );
    """)
    return browser, ctx


# ─── Timing helpers ───────────────────────────────────────────────────────────

async def human_delay(min_s: float = 2.5, max_s: float = 6.0):
    """Random pause to mimic human browsing speed."""
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)


async def micro_delay():
    """Very short delay for actions within a page (scroll, click, etc.)."""
    await asyncio.sleep(random.uniform(0.3, 1.2))


async def scroll_to_bottom(page, steps: int = 5):
    """Gradually scroll page to trigger lazy-load content."""
    for i in range(1, steps + 1):
        await page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {i / steps})")
        await asyncio.sleep(random.uniform(0.3, 0.8))


# ─── Retry decorator ─────────────────────────────────────────────────────────

def async_retry(max_attempts: int = 3, backoff_base: float = 2.0, exceptions=(Exception,)):
    """Exponential-backoff retry decorator for async functions."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> Any:
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        log.error("  ✗ %s failed after %d attempts: %s", fn.__name__, max_attempts, exc)
                        raise
                    wait = backoff_base ** attempt + random.uniform(0, 1)
                    log.warning("  ↺ Attempt %d/%d failed: %s — retrying in %.1fs",
                                attempt, max_attempts, exc, wait)
                    await asyncio.sleep(wait)
        return wrapper
    return decorator


# ─── Database helpers ─────────────────────────────────────────────────────────

def upsert_product(data: dict) -> str:
    """
    Upsert product into Supabase. Returns the product id.
    Unique constraint on (retailer, retailer_id) handles deduplication.
    Price history is appended automatically via DB trigger.
    """
    data["last_scraped"] = datetime.now(timezone.utc).isoformat()
    res = (
        supabase.table("products")
        .upsert(data, on_conflict="retailer,retailer_id")
        .execute()
    )
    return res.data[0]["id"]


def bulk_upsert_products(products: list[dict]) -> tuple[int, int]:
    """Upsert a batch of products. Returns (success_count, fail_count)."""
    success, failed = 0, 0
    for p in products:
        try:
            upsert_product(p)
            success += 1
        except Exception as e:
            model = p.get("model", "?")[:50]
            log.error("  ✗ DB upsert failed for '%s': %s", model, e)
            failed += 1
    return success, failed


def get_active_alerts() -> list[dict]:
    """Fetch all active price drop alerts."""
    res = (
        supabase.table("alerts")
        .select("*, products(model, current_price, retailer, affiliate_url, image_url)")
        .eq("active", True)
        .execute()
    )
    return res.data or []


def log_alert_event(alert_id: str, product_id: str, old_price: float,
                    new_price: float, channel: str, status: str, error_msg: str = None):
    """Record an alert dispatch attempt in alert_events."""
    supabase.table("alert_events").insert({
        "alert_id": alert_id,
        "product_id": product_id,
        "old_price": old_price,
        "new_price": new_price,
        "channel": channel,
        "status": status,
        "error_msg": error_msg,
    }).execute()


# ─── Price helpers ────────────────────────────────────────────────────────────

def parse_aed_price(text: str) -> Optional[float]:
    """Extract numeric AED price from various string formats."""
    if not text:
        return None
    cleaned = text.replace(",", "").replace("AED", "").replace("د.إ", "").strip()
    m = re.search(r"[\d]+\.?\d*", cleaned) if cleaned else None
    return float(m.group()) if m else None


# Import re here to avoid circular issues at module level
import re
