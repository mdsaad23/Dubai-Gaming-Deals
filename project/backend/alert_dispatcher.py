"""
GulfDeals — Alert Dispatcher
Checks active price-drop alerts against current product prices,
then sends notifications via email (Resend) and WhatsApp (Twilio).

Run after every scrape cycle:
    cd project/backend
    python alert_dispatcher.py
"""

import os, sys, logging, json, re
from datetime import datetime, timezone
from typing import Optional
import httpx                    # lightweight async HTTP (fallback: requests)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrapers"))
from base import supabase, log_alert_event, log

# ─── Config ───────────────────────────────────────────────────────────────────
RESEND_API_KEY       = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM          = os.environ.get("RESEND_FROM", "GulfDeals <alerts@gulfdeals.ae>")

TWILIO_ACCOUNT_SID   = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN    = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

SITE_URL = os.environ.get("SITE_URL", "https://gulfdeals.ae")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [alert_dispatcher] %(levelname)s — %(message)s",
)


# ─── Email (Resend) ───────────────────────────────────────────────────────────

def send_email(to: str, subject: str, html: str) -> bool:
    """Send a transactional email via Resend API. Returns True on success."""
    if not RESEND_API_KEY:
        log.warning("RESEND_API_KEY not set — skipping email to %s", to)
        return False

    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": RESEND_FROM,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            log.info("  ✓ Email sent to %s (id=%s)", to, resp.json().get("id"))
            return True
        else:
            log.error("  ✗ Resend error %d: %s", resp.status_code, resp.text[:200])
            return False
    except Exception as e:
        log.error("  ✗ Email send exception: %s", e)
        return False


def build_price_drop_email(product: dict, alert: dict, old_price: float, new_price: float) -> tuple[str, str]:
    """Build email subject and HTML body for a price drop notification."""
    name    = product.get("model", "Gaming Product")[:60]
    savings = old_price - new_price
    pct     = round((savings / old_price) * 100) if old_price > 0 else 0
    url     = product.get("affiliate_url") or product.get("product_url", SITE_URL)
    img     = product.get("image_url", "")
    retailer = product.get("retailer", "").replace("_", " ").title()

    subject = f"🔥 Price Drop! {name[:40]} — AED {new_price:.0f} ({pct}% off)"

    img_block = f'<img src="{img}" alt="{name}" style="max-width:200px;border-radius:8px;" /><br/>' if img else ""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="font-family:Arial,sans-serif;background:#0f0f0f;color:#fff;padding:24px;">
  <div style="max-width:560px;margin:0 auto;background:#1a1a1a;border-radius:12px;overflow:hidden;">
    <div style="background:#00ff88;padding:16px 24px;">
      <h1 style="color:#000;margin:0;font-size:20px;">GulfDeals Price Alert</h1>
    </div>
    <div style="padding:24px;">
      {img_block}
      <h2 style="color:#00ff88;margin-top:0;">{name}</h2>
      <p style="color:#aaa;">Available on <strong style="color:#fff;">{retailer}</strong></p>

      <table style="width:100%;border-collapse:collapse;margin:16px 0;">
        <tr>
          <td style="padding:8px;color:#aaa;">Was</td>
          <td style="padding:8px;text-decoration:line-through;color:#888;">AED {old_price:.2f}</td>
        </tr>
        <tr>
          <td style="padding:8px;color:#aaa;">Now</td>
          <td style="padding:8px;color:#00ff88;font-size:24px;font-weight:bold;">AED {new_price:.2f}</td>
        </tr>
        <tr>
          <td style="padding:8px;color:#aaa;">You save</td>
          <td style="padding:8px;color:#ff4444;font-weight:bold;">AED {savings:.2f} ({pct}% off)</td>
        </tr>
      </table>

      <a href="{url}" style="display:inline-block;background:#00ff88;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;margin-top:8px;">
        View Deal →
      </a>

      <hr style="border-color:#333;margin:24px 0;"/>
      <p style="color:#555;font-size:12px;">
        You're receiving this because you set a price alert on GulfDeals.
        <a href="{SITE_URL}/unsubscribe?token={alert.get('token', '')}" style="color:#555;">Unsubscribe</a>
      </p>
    </div>
  </div>
</body>
</html>"""

    return subject, html


# ─── WhatsApp (Twilio) ────────────────────────────────────────────────────────

def send_whatsapp(to_phone: str, message: str) -> bool:
    """
    Send a WhatsApp message via Twilio.
    `to_phone` must be E.164 format e.g. +971501234567
    Returns True on success.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        log.warning("Twilio credentials not set — skipping WhatsApp to %s", to_phone)
        return False

    to_wa = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone

    try:
        resp = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            data={
                "From": TWILIO_WHATSAPP_FROM,
                "To":   to_wa,
                "Body": message,
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            sid = resp.json().get("sid", "")
            log.info("  ✓ WhatsApp sent to %s (sid=%s)", to_phone, sid)
            return True
        else:
            log.error("  ✗ Twilio error %d: %s", resp.status_code, resp.text[:200])
            return False
    except Exception as e:
        log.error("  ✗ WhatsApp send exception: %s", e)
        return False


def build_whatsapp_message(product: dict, old_price: float, new_price: float) -> str:
    """Build a compact WhatsApp message for a price drop alert."""
    name    = product.get("model", "Gaming Product")[:60]
    savings = old_price - new_price
    pct     = round((savings / old_price) * 100) if old_price > 0 else 0
    url     = product.get("affiliate_url") or product.get("product_url", SITE_URL)

    return (
        f"🎮 *GulfDeals Price Alert!*\n\n"
        f"*{name}*\n\n"
        f"💰 Was: AED {old_price:.0f}\n"
        f"🔥 Now: AED {new_price:.0f}\n"
        f"💸 Save: AED {savings:.0f} ({pct}% off)\n\n"
        f"👉 {url}\n\n"
        f"_Reply STOP to unsubscribe_"
    )


# ─── Alert evaluation ─────────────────────────────────────────────────────────

def should_fire_alert(alert: dict, current_price: float) -> tuple[bool, float]:
    """
    Check whether an alert should fire.
    Returns (should_fire, old_price_snapshot).

    Fires when:
    - alert_type == 'price_drop': current_price < previous scrape price (any drop)
    - alert_type == 'price_drop' with target_price set: current <= target_price
    - alert_type == 'any_change': price differs from last alert event
    """
    alert_type   = alert.get("alert_type", "price_drop")
    target_price = alert.get("target_price")

    # Get last known price from price_history for this product
    product_id = alert.get("product_id")
    old_price  = None

    if product_id:
        try:
            # Get second-to-last price point (last price before current scrape)
            res = (
                supabase.table("price_history")
                .select("price")
                .eq("product_id", product_id)
                .order("scraped_at", desc=True)
                .limit(2)
                .execute()
            )
            rows = res.data or []
            if len(rows) >= 2:
                old_price = float(rows[1]["price"])
            elif len(rows) == 1:
                old_price = float(rows[0]["price"])
        except Exception as e:
            log.warning("  ✗ Could not fetch price history for alert %s: %s", alert.get("id"), e)

    if old_price is None:
        old_price = current_price

    if alert_type == "price_drop":
        if target_price:
            return current_price <= float(target_price), old_price
        else:
            return current_price < old_price, old_price

    elif alert_type == "any_change":
        return current_price != old_price, old_price

    return False, old_price


def fetch_active_alerts_with_products() -> list[dict]:
    """Fetch all active alerts joined with current product data."""
    try:
        res = (
            supabase.table("alerts")
            .select(
                "id, product_id, channel, destination, target_price, alert_type, token, "
                "products(id, model, brand, retailer, current_price, affiliate_url, image_url, category)"
            )
            .eq("active", True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        log.error("Failed to fetch alerts: %s", e)
        return []


def deactivate_alert(alert_id: str):
    """Deactivate an alert after successful dispatch (one-shot alerts)."""
    try:
        supabase.table("alerts").update({"active": False}).eq("id", alert_id).execute()
    except Exception as e:
        log.warning("Could not deactivate alert %s: %s", alert_id, e)


# ─── Main dispatch loop ───────────────────────────────────────────────────────

def dispatch_alerts():
    """Main entry: evaluate all active alerts and dispatch notifications."""
    log.info("=== GulfDeals Alert Dispatcher ===")

    alerts = fetch_active_alerts_with_products()
    log.info("Found %d active alerts to evaluate", len(alerts))

    sent_count  = 0
    skip_count  = 0
    error_count = 0

    for alert in alerts:
        try:
            product = alert.get("products")
            if not product:
                log.debug("  Skip alert %s — product not found", alert.get("id"))
                skip_count += 1
                continue

            product_id    = product["id"]
            current_price = float(product["current_price"])
            channel       = alert["channel"]
            destination   = alert["destination"]

            should_fire, old_price = should_fire_alert(alert, current_price)

            if not should_fire:
                skip_count += 1
                continue

            log.info("  Firing alert %s → %s via %s (%.2f → %.2f AED)",
                     alert["id"], destination, channel, old_price, current_price)

            success = False

            if channel == "email":
                subject, html = build_price_drop_email(product, alert, old_price, current_price)
                success = send_email(destination, subject, html)

            elif channel == "whatsapp":
                msg = build_whatsapp_message(product, old_price, current_price)
                success = send_whatsapp(destination, msg)

            status    = "sent" if success else "failed"
            error_msg = None if success else f"Dispatch failed for channel {channel}"

            log_alert_event(
                alert_id=alert["id"],
                product_id=product_id,
                old_price=old_price,
                new_price=current_price,
                channel=channel,
                status=status,
                error_msg=error_msg,
            )

            if success:
                sent_count += 1
                # One-shot alerts (target_price set) deactivate after firing
                if alert.get("target_price"):
                    deactivate_alert(alert["id"])
            else:
                error_count += 1

        except Exception as e:
            log.error("  ✗ Unhandled alert error for %s: %s", alert.get("id"), e)
            error_count += 1

    log.info("\n✓ Done. %d sent, %d skipped (no price change), %d errors.",
             sent_count, skip_count, error_count)


if __name__ == "__main__":
    dispatch_alerts()
