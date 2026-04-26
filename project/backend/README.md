# GulfDeals — Backend Architecture

## Overview

A fully automated price-tracking pipeline: scrapers pull product data from UAE
retailers on a schedule, store it in Supabase (PostgreSQL), trigger alerts via
email and WhatsApp when prices drop, and expose a REST API to the frontend.

```
┌─────────────────────────────────────────────────────────────┐
│                        SCRAPERS                             │
│   amazon_ae.py  │  noon.py  │  sharaf.py  │  emax.py       │
└────────────────────────┬────────────────────────────────────┘
                         │ upsert products + price history
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    SUPABASE (PostgreSQL)                     │
│  products  │  price_history  │  alerts  │  alert_events     │
└──────┬──────────────────────────────┬────────────────────────┘
       │ auto-REST / PostgREST        │ pg_cron or Edge Fn
       ▼                              ▼
┌─────────────┐              ┌────────────────────┐
│  Frontend   │              │  Alert Dispatcher  │
│  (index.html│              │  Resend (email)     │
│   React)    │              │  Twilio (WhatsApp)  │
└─────────────┘              └────────────────────┘
```

---

## Stack

| Layer           | Tool                        | Notes                                      |
|-----------------|-----------------------------|--------------------------------------------|
| Database        | Supabase (PostgreSQL 15)    | Hosted, RLS, realtime, free tier           |
| Scraping        | Python 3.11 + Playwright    | Handles JS-rendered pages                  |
| Anti-block      | Rotating residential proxies| See IP section below                       |
| Scheduler       | GitHub Actions cron         | Free, version-controlled, easy secrets     |
| Email alerts    | Resend API                  | 3,000 emails/mo free                       |
| WhatsApp alerts | Twilio WhatsApp API         | Sandbox free, production ~$0.005/msg       |
| API             | Supabase auto-REST          | No extra server needed                     |
| Secret storage  | GitHub Actions Secrets      | SUPABASE_URL, SUPABASE_KEY, etc.           |

---

## Database Schema

See `schema.sql` for full DDL. Tables:

### `products`
Primary product catalogue. One row per product per retailer listing.

| Column         | Type      | Notes                                        |
|----------------|-----------|----------------------------------------------|
| id             | uuid PK   | auto-generated                               |
| category       | text      | 'laptop' \| 'cpu' \| 'gpu'                  |
| brand          | text      | e.g. 'ASUS', 'NVIDIA'                        |
| model          | text      | e.g. 'ROG Strix G16'                         |
| retailer       | text      | 'amazon_ae' \| 'noon' \| 'sharaf_dg'        |
| product_url    | text      | Retailer product page URL                    |
| affiliate_url  | text      | Affiliate-tagged URL                         |
| image_url      | text      |                                              |
| current_price  | numeric   | Latest scraped price in AED                  |
| original_price | numeric   | Retailer's "was" price                       |
| discount_pct   | numeric   | Computed: (original-current)/original * 100  |
| specs          | jsonb     | Flexible: {screen, cpu, gpu, ram, ...}       |
| is_available   | bool      | False if out of stock                        |
| is_hot         | bool      | True if discount ≥ 20% and rating ≥ 4.5      |
| rating         | numeric   |                                              |
| review_count   | int       |                                              |
| last_scraped   | timestamptz |                                            |
| created_at     | timestamptz | auto                                       |

### `price_history`
Append-only log — never update, only insert.

| Column     | Type        | Notes                        |
|------------|-------------|------------------------------|
| id         | bigint PK   | auto                         |
| product_id | uuid FK     | → products.id                |
| price      | numeric     | AED                          |
| scraped_at | timestamptz | when this price was observed |

### `alerts`
User subscriptions for price drop notifications.

| Column       | Type        | Notes                                    |
|--------------|-------------|------------------------------------------|
| id           | uuid PK     |                                          |
| product_id   | uuid FK     | → products.id (null = all new deals)    |
| channel      | text        | 'email' \| 'whatsapp'                   |
| destination  | text        | email address or E.164 phone number      |
| target_price | numeric     | Notify when price ≤ this value           |
| alert_type   | text        | 'price_drop' \| 'any_change' \| 'new_deal' |
| active       | bool        | false = unsubscribed                     |
| created_at   | timestamptz |                                          |

### `alert_events`
Audit log of every notification sent.

| Column     | Type        |
|------------|-------------|
| id         | bigint PK   |
| alert_id   | uuid FK     |
| product_id | uuid FK     |
| old_price  | numeric     |
| new_price  | numeric     |
| sent_at    | timestamptz |
| channel    | text        |
| status     | text        | 'sent' \| 'failed'  |

---

## Scraping Pipeline

### Run order
1. `scrapers/amazon_ae.py` — scrapes laptops, CPUs, GPUs
2. `scrapers/noon.py`
3. `scrapers/sharaf_dg.py` (future)
4. `alert_dispatcher.py` — checks price drops, sends notifications

### Schedule (GitHub Actions cron)
```
Every 4 hours:  scrape + alert_dispatcher
Every midnight: mark stale products as unavailable
```

---

## IP Blacklisting — The Reality

**Yes, Amazon.ae and Noon will block you.** Here's exactly what happens:

### What they detect
| Signal                     | Amazon.ae | Noon    |
|----------------------------|-----------|---------|
| Datacenter / cloud IPs     | ✅ blocked | ✅ blocked |
| Missing browser fingerprint | ✅        | ✅      |
| Headless browser headers   | ✅        | Partial |
| Request rate (>1 req/5s)   | ✅ CAPTCHA | ✅      |
| Scraping patterns          | ✅        | ✅      |
| Missing cookies/session     | ✅        | Partial |

### Consequences
- **Amazon.ae**: First offence = CAPTCHA wall on that IP. Repeat = 24h ban. AWS/GCP IPs
  get permanent bans within minutes. Residential IPs last longer.
- **Noon**: Less aggressive than Amazon. Rate-limit before ban. CAPTCHAs appear
  after ~50 rapid requests from same IP.

### Mitigation strategy (what's in the scrapers)
1. **Residential rotating proxies** — use BrightData, Oxylabs, or SmartProxy.
   Cost: ~$15–30/mo for this use case. Essential. Datacenter proxies don't work.
2. **Random delays** — 3–8 seconds between requests (already in the code)
3. **Realistic browser profile** — Playwright with stealth plugin spoofs fingerprint
4. **Rate limiting** — max 10 products per session, then rotate IP + restart
5. **Session cookies** — maintain cookies across requests like a real browser
6. **Off-peak scraping** — run at 3am, 7am, 1pm, 7pm UAE time

### Safer alternative: official APIs
- **Amazon Product Advertising API** — free, official, no ban risk.
  Apply at: https://affiliate-program.amazon.com/
  Rate limit: 1 req/sec, 8,640/day — sufficient for this use case.
  Returns price, image, specs, affiliate URL automatically.
- **Noon**: No public API. Scraping is the only option.

### Recommended setup
```
Phase 1 (launch): Amazon PA API (free, zero ban risk) + manual Noon scraping
                  with residential proxies for initial data.
Phase 2 (scale):  Add Sharaf DG, Emax with residential proxies + retry logic.
Phase 3 (growth): Consider a managed scraping service (Apify, ScrapeOps) if
                  proxy management becomes a burden (~$50/mo).
```

---

## Environment Variables

```bash
# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...   # service role key (never expose to frontend)

# Proxy (BrightData example)
PROXY_HOST=brd.superproxy.io
PROXY_PORT=22225
PROXY_USER=brd-customer-xxx-zone-residential
PROXY_PASS=xxx

# Resend (email)
RESEND_API_KEY=re_xxx

# Twilio (WhatsApp)
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

# Amazon PA API (safer alternative to scraping)
AMAZON_ACCESS_KEY=xxx
AMAZON_SECRET_KEY=xxx
AMAZON_ASSOCIATE_TAG=gulfdeals-21
```

---

## Folder Structure

```
backend/
├── README.md               ← this file
├── schema.sql              ← Supabase DDL
├── requirements.txt        ← Python deps
├── scrapers/
│   ├── base.py             ← shared browser setup, proxy, DB client
│   ├── amazon_ae.py        ← Amazon.ae scraper
│   └── noon.py             ← Noon scraper
├── alert_dispatcher.py     ← checks price drops, sends email/WhatsApp
└── .github/
    └── workflows/
        └── scrape.yml      ← GitHub Actions cron schedule
```
