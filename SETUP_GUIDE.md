# GulfDeals — Setup Guide & Project Status

> **Date**: May 2026  
> **Branch**: `claude/backend-requirements-scraper-2KsBK`

---

## Table of Contents

1. [What Has Been Built (Code Complete)](#1-what-has-been-built)
2. [Project File Structure](#2-project-file-structure)
3. [Manual Steps Required From You](#3-manual-steps-required-from-you)
4. [Remaining Code Work (Not Yet Done)](#4-remaining-code-work)
5. [How It All Works Together](#5-how-it-all-works-together)
6. [Environment Variables Reference](#6-environment-variables-reference)

---

## 1. What Has Been Built

All of the following is complete, written, and committed locally.

### Backend Scraping Engine

| File | Purpose |
|------|---------|
| `project/backend/scrapers/spec_parser.py` | Core spec extraction — 35+ GPU chips, 30+ CPU models, laptop spec detection using regex + lookup tables |
| `project/backend/scrapers/base.py` | Shared Playwright helpers — stealth browser, retry decorator, Supabase bulk upsert, price parser |
| `project/backend/scrapers/amazon_ae.py` | Amazon.ae scraper — 18 search targets (laptops, CPUs, GPUs), 2-phase pipeline: search results → detail pages |
| `project/backend/scrapers/noon.py` | Noon scraper — 17 search targets, `__NEXT_DATA__` JSON parsing + DOM fallback |
| `project/backend/scrapers/__init__.py` | Makes scrapers a Python package |
| `project/backend/alert_dispatcher.py` | Price drop alerts via Resend (email) and Twilio (WhatsApp) |
| `project/backend/run_all.py` | Orchestrator — runs Amazon → Noon → Alerts with configurable flags |

### Database

| File | Purpose |
|------|---------|
| `project/backend/schema.sql` | Complete PostgreSQL schema v2 with products, price_history, alerts, alert_events tables, triggers, views, RLS policies |

**Key schema features:**
- `products` table with `specs` JSONB column for all category-specific fields
- `discount_pct` auto-calculated as a generated column
- `is_hot` auto-updated by trigger (≥20% discount + ≥4.3 rating + available)
- `price_history` records every price change automatically via trigger
- Three views: `deals_with_history`, `deal_stats`, `top_deals`
- pg_cron jobs for: purging 90-day-old price history, marking stale products unavailable, refreshing `is_hot` daily
- Row Level Security (RLS): public read access, service role write access

### Infrastructure

| File | Purpose |
|------|---------|
| `project/backend/requirements.txt` | Python dependencies: supabase, playwright, httpx, python-dotenv |
| `project/backend/.github/workflows/scrape.yml` | GitHub Actions — runs scrapers 4× daily (5am/11am/5pm/11pm UAE time), with manual trigger per-scraper |
| `.env.example` | Template for all required environment variables |

---

## 2. Project File Structure

```
Dubai-Gaming-Deals/
├── .env.example                          ← Template for environment variables
├── SETUP_GUIDE.md                        ← This file
├── project/
│   ├── index.html                        ← Frontend (React 18 CDN, currently mock data)
│   └── backend/
│       ├── schema.sql                    ← Run this in Supabase SQL Editor
│       ├── requirements.txt              ← pip install -r requirements.txt
│       ├── run_all.py                    ← Main orchestrator
│       ├── alert_dispatcher.py           ← Email + WhatsApp alerts
│       ├── .github/
│       │   └── workflows/
│       │       └── scrape.yml            ← GitHub Actions cron
│       └── scrapers/
│           ├── __init__.py
│           ├── spec_parser.py            ← Spec extraction engine
│           ├── base.py                   ← Shared Playwright + DB helpers
│           ├── amazon_ae.py              ← Amazon.ae scraper
│           └── noon.py                  ← Noon scraper
```

---

## 3. Manual Steps Required From You

Complete these **in order**. Each step has a prerequisite.

---

### STEP 1 — Create a Supabase Project

**Where**: https://supabase.com  
**Time**: ~5 minutes

1. Sign up / log in at https://supabase.com
2. Click **New Project**
3. Choose a name (e.g., `gulfdeals`), set a strong database password, choose region **Middle East (Bahrain)** for lowest latency from UAE
4. Wait ~2 minutes for the project to provision
5. Go to **Settings → API** and copy:
   - **Project URL** → your `SUPABASE_URL` (looks like `https://abcdefgh.supabase.co`)
   - **service_role** key (not `anon`) → your `SUPABASE_SERVICE_KEY` (starts with `eyJ...`)
   - **anon** key → your `SUPABASE_ANON_KEY` (needed for frontend)

> **Important**: The `service_role` key has full database access. Never expose it in frontend code or commit it to git.

---

### STEP 2 — Run the Database Schema

**Where**: Supabase Dashboard → SQL Editor  
**Time**: ~2 minutes

1. Open your Supabase project dashboard
2. Click **SQL Editor** in the left sidebar
3. Click **New query**
4. Open the file `project/backend/schema.sql` from this repo
5. Copy the entire contents and paste into the SQL editor
6. Click **Run** (or press Ctrl+Enter)
7. You should see "Success. No rows returned" — this is correct

**Verify it worked**: Click **Table Editor** in the sidebar and confirm you see these tables:
- `products`
- `price_history`
- `alerts`
- `alert_events`

---

### STEP 3 — Set Up a Residential Proxy (Strongly Recommended)

**Why**: Amazon.ae and Noon actively block datacenter IPs (GitHub Actions uses AWS IPs which are blocked). Without a residential proxy, scrapers will get CAPTCHAs within minutes.

**Recommended provider**: BrightData (https://brightdata.com)  
**Alternative**: Oxylabs (https://oxylabs.io)

**BrightData setup**:
1. Sign up at https://brightdata.com
2. Go to **Proxies & Scraping** → **Residential**
3. Create a new zone named `gulfdeals`
4. Note your credentials:
   - Host: `brd.superproxy.io`
   - Port: `22225`
   - Username: your BrightData username
   - Password: your BrightData password

**Cost**: ~$15–20 for first month (scraping ~1,000 pages/day)

> **Without a proxy**: Scrapers will still run locally but will be blocked quickly. Fine for testing.

---

### STEP 4 — Set Up Resend for Email Alerts (Optional)

**Where**: https://resend.com  
**Time**: ~10 minutes  
**Free tier**: 3,000 emails/month

1. Sign up at https://resend.com
2. Add and verify your domain (e.g., `yourdomain.com`) in **Domains**
3. Go to **API Keys** → **Create API Key**
4. Copy the key (starts with `re_`)
5. Your `RESEND_FROM` will be something like: `GulfDeals <alerts@yourdomain.com>`

> **No domain?** Resend allows sending from `onboarding@resend.dev` for testing only.

---

### STEP 5 — Set Up Twilio for WhatsApp Alerts (Optional)

**Where**: https://twilio.com  
**Time**: ~15 minutes

1. Sign up at https://twilio.com
2. Go to **Messaging → Senders → WhatsApp Senders**
3. For testing, use the **Sandbox** (no approval needed):
   - Sandbox number: `+14155238886`
   - Send "join [your-keyword]" to that number from your WhatsApp first
4. For production: Apply for WhatsApp Business API approval (~1-2 weeks)
5. Copy from **Account Info**:
   - `TWILIO_ACCOUNT_SID` (starts with `AC`)
   - `TWILIO_AUTH_TOKEN`

---

### STEP 6 — Create Your `.env` File

**Where**: `project/backend/.env` (create this file, it's git-ignored)

Copy `.env.example` to `project/backend/.env` and fill in your values:

```bash
cp .env.example project/backend/.env
```

Then edit `project/backend/.env` with your actual credentials:

```env
SUPABASE_URL=https://your-actual-project-id.supabase.co
SUPABASE_SERVICE_KEY=eyJ...your-service-role-key...

PROXY_HOST=brd.superproxy.io
PROXY_PORT=22225
PROXY_USER=your-brightdata-username
PROXY_PASS=your-brightdata-password

RESEND_API_KEY=re_your_actual_key
RESEND_FROM=GulfDeals <alerts@yourdomain.com>

TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_actual_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

SITE_URL=https://yourdomain.com
AMAZON_AFFILIATE_TAG=yourtag-21
```

---

### STEP 7 — Add GitHub Actions Secrets

**Where**: GitHub → Your repo → Settings → Secrets and variables → Actions  
**Time**: ~5 minutes

Add each of the following as a **Repository secret** (New repository secret):

| Secret Name | Value |
|-------------|-------|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Your service_role key |
| `PROXY_HOST` | `brd.superproxy.io` (or leave blank to skip) |
| `PROXY_PORT` | `22225` |
| `PROXY_USER` | Your proxy username |
| `PROXY_PASS` | Your proxy password |
| `RESEND_API_KEY` | Your Resend API key |
| `RESEND_FROM` | e.g. `GulfDeals <alerts@yourdomain.com>` |
| `TWILIO_ACCOUNT_SID` | Your Twilio SID |
| `TWILIO_AUTH_TOKEN` | Your Twilio auth token |
| `TWILIO_WHATSAPP_FROM` | `whatsapp:+14155238886` |
| `SITE_URL` | Your site's public URL |

> **Note**: Proxy secrets can be left blank for initial testing — scrapers will run without a proxy (expect some blocks).

---

### STEP 8 — Enable pg_cron in Supabase

**Why**: The schema uses pg_cron for automated maintenance (purging old price history, marking stale products, etc.)

1. In your Supabase dashboard, go to **Database → Extensions**
2. Search for `pg_cron`
3. Toggle it **ON**

> pg_cron may already be enabled in newer Supabase projects.

---

### STEP 9 — Test the Scrapers Locally

```bash
cd project/backend

# Install dependencies
pip install -r requirements.txt
playwright install chromium --with-deps

# Test Amazon scraper only
python run_all.py --amazon

# Test Noon scraper only  
python run_all.py --noon

# Run everything
python run_all.py
```

Watch the logs — you should see products being upserted to Supabase.  
Verify in **Supabase → Table Editor → products** that rows are appearing.

---

### STEP 10 — Deploy Frontend (When Ready)

The frontend (`project/index.html`) currently shows **mock data**. After the frontend integration is complete (see Section 4), you'll need to:

1. Add your `SUPABASE_URL` and `SUPABASE_ANON_KEY` to the frontend config section in `index.html`
2. Host the frontend — options:
   - **Vercel**: Connect your GitHub repo, set root to `project/`, deploy instantly (free)
   - **Netlify**: Same process, also free
   - **GitHub Pages**: Enable in repo Settings → Pages, set source to `project/` folder
3. Update `SITE_URL` in your `.env` and GitHub secrets to the deployed URL

---

### STEP 11 — Set Up Amazon Associates (Optional but Recommended)

**Where**: https://affiliate-program.amazon.ae  
**Why**: Earns commission on sales from your links

1. Apply at the Amazon Associates program for UAE
2. Once approved, get your **Tracking ID** (e.g., `gulfdeals-21`)
3. Update `AMAZON_AFFILIATE_TAG` in `project/backend/.env` and your GitHub secrets
4. The scraper already appends `?tag=your-tag` to all Amazon product URLs automatically

---

## 4. Remaining Code Work

The following work is **not yet done** but does not require manual input from you:

### Frontend ↔ Supabase Integration (Pending)

**File**: `project/index.html`  
**Current state**: Uses hardcoded mock data arrays (`LAPTOPS`, `CPUS`, `GPUS`)

**Work needed**:
- [ ] Add Supabase JS client CDN script
- [ ] Add config block for `SUPABASE_URL` and `SUPABASE_ANON_KEY` (placeholder — you fill in after Step 1)
- [ ] Replace mock data arrays with `useEffect` fetching from Supabase `products` table
- [ ] Map DB field names → frontend field names:
  - `current_price` → `salePrice`
  - `original_price` → `originalPrice`
  - `discount_pct` → `discount`
  - `is_hot` → `hot`
  - `review_count` → `reviews`
  - `amazon_ae` → `amazon` (retailer key)
- [ ] Add loading spinner and error state
- [ ] Wire `AlertModal` form to actually INSERT into Supabase `alerts` table
- [ ] Update stats bar to use live counts from `deal_stats` view

---

## 5. How It All Works Together

```
GitHub Actions (cron 4×/day)
        │
        ▼
run_all.py (orchestrator)
    ├── amazon_ae.py ──────────────────────────────────┐
    │   ├── Search pages (18 queries × 3 pages)        │
    │   └── Detail pages (up to 120 products)          │
    ├── noon.py ─────────────────────────────────────  │
    │   ├── __NEXT_DATA__ JSON parsing                 │── Supabase PostgreSQL
    │   └── DOM fallback scraping                      │   ├── products table
    └── alert_dispatcher.py                            │   ├── price_history (auto)
        ├── Query price changes in Supabase            │   ├── alerts table
        ├── Send email alerts via Resend        ───────┘   └── alert_events table
        └── Send WhatsApp alerts via Twilio

Frontend (index.html)
    ├── Fetches from Supabase REST API (anon key)
    ├── Displays products with filters + sort
    └── Alert subscription form → INSERT to alerts table
```

---

## 6. Environment Variables Reference

| Variable | Required | Where Used | Description |
|----------|----------|------------|-------------|
| `SUPABASE_URL` | Yes | Backend, Frontend | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Yes | Backend only | Service role key (full DB access) |
| `SUPABASE_ANON_KEY` | Yes | Frontend only | Anon key (read-only public access) |
| `PROXY_HOST` | Recommended | Scrapers | Residential proxy host |
| `PROXY_PORT` | Recommended | Scrapers | Residential proxy port |
| `PROXY_USER` | Recommended | Scrapers | Proxy username |
| `PROXY_PASS` | Recommended | Scrapers | Proxy password |
| `RESEND_API_KEY` | Optional | Alert dispatcher | Email sending |
| `RESEND_FROM` | Optional | Alert dispatcher | Sender address |
| `TWILIO_ACCOUNT_SID` | Optional | Alert dispatcher | WhatsApp sending |
| `TWILIO_AUTH_TOKEN` | Optional | Alert dispatcher | WhatsApp auth |
| `TWILIO_WHATSAPP_FROM` | Optional | Alert dispatcher | WhatsApp sender number |
| `SITE_URL` | Optional | Alert emails | Base URL for links in emails |
| `AMAZON_AFFILIATE_TAG` | Optional | Amazon scraper | Affiliate tracking ID |

---

## Quick Start Summary

**Minimum to get scraping working**:
1. Create Supabase project → get `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`
2. Run `schema.sql` in Supabase SQL Editor
3. Create `project/backend/.env` with Supabase credentials
4. `pip install -r requirements.txt && playwright install chromium --with-deps`
5. `python run_all.py`

**To enable automated scraping via GitHub Actions**:
6. Push this branch to GitHub
7. Add Supabase secrets in GitHub → Settings → Secrets
8. Workflow runs automatically at 1am, 7am, 1pm, 7pm UTC

**To enable price drop alerts**:
9. Sign up for Resend (email) and/or Twilio (WhatsApp)
10. Add those secrets to both `.env` and GitHub Secrets
