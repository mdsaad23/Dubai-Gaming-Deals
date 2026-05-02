"""
GulfDeals — Orchestrator
Runs all scrapers sequentially then dispatches price alerts.
Designed for both local development and GitHub Actions CI.

Usage:
    cd project/backend
    python run_all.py              # run everything
    python run_all.py --amazon     # only Amazon.ae
    python run_all.py --noon       # only Noon
    python run_all.py --alerts     # only dispatch alerts
    python run_all.py --no-alerts  # skip alert dispatch
"""

import asyncio
import argparse
import logging
import sys
import os
import time

# Ensure scrapers dir is on path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrapers"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [orchestrator] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("orchestrator")

# Minimum seconds to wait between scrapers to avoid rate-limiting
INTER_SCRAPER_DELAY = 30


def parse_args():
    p = argparse.ArgumentParser(description="GulfDeals scraper orchestrator")
    p.add_argument("--amazon",    action="store_true", help="Run Amazon.ae scraper only")
    p.add_argument("--noon",      action="store_true", help="Run Noon scraper only")
    p.add_argument("--alerts",    action="store_true", help="Run alert dispatcher only")
    p.add_argument("--no-alerts", action="store_true", help="Skip alert dispatcher")
    return p.parse_args()


async def run_amazon():
    """Run the Amazon.ae scraper."""
    log.info("━━━ Starting Amazon.ae scraper ━━━")
    start = time.time()
    try:
        # Import and run amazon scraper's main function
        import amazon_ae
        await amazon_ae.main()
        elapsed = time.time() - start
        log.info("━━━ Amazon.ae scraper done in %.0fs ━━━", elapsed)
        return True
    except Exception as e:
        log.error("━━━ Amazon.ae scraper FAILED: %s ━━━", e)
        return False


async def run_noon():
    """Run the Noon.ae scraper."""
    log.info("━━━ Starting Noon.ae scraper ━━━")
    start = time.time()
    try:
        import noon
        await noon.main()
        elapsed = time.time() - start
        log.info("━━━ Noon.ae scraper done in %.0fs ━━━", elapsed)
        return True
    except Exception as e:
        log.error("━━━ Noon.ae scraper FAILED: %s ━━━", e)
        return False


def run_alerts():
    """Run the alert dispatcher (synchronous)."""
    log.info("━━━ Starting alert dispatcher ━━━")
    start = time.time()
    try:
        # Import from parent directory
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import alert_dispatcher
        alert_dispatcher.dispatch_alerts()
        elapsed = time.time() - start
        log.info("━━━ Alert dispatcher done in %.0fs ━━━", elapsed)
        return True
    except Exception as e:
        log.error("━━━ Alert dispatcher FAILED: %s ━━━", e)
        return False


async def main():
    args = parse_args()

    # Determine which components to run
    run_amazon_flag  = args.amazon or (not args.noon  and not args.alerts)
    run_noon_flag    = args.noon   or (not args.amazon and not args.alerts)
    run_alerts_flag  = args.alerts or (not args.no_alerts and not args.amazon and not args.noon)

    # If only --amazon or --noon specified, don't run alerts unless --alerts is also given
    if args.amazon or args.noon:
        run_alerts_flag = args.alerts

    results = {}

    total_start = time.time()
    log.info("GulfDeals Orchestrator — starting run")
    log.info("  Amazon.ae:  %s", "YES" if run_amazon_flag else "NO")
    log.info("  Noon.ae:    %s", "YES" if run_noon_flag else "NO")
    log.info("  Alerts:     %s", "YES" if run_alerts_flag else "NO")

    if run_amazon_flag:
        results["amazon"] = await run_amazon()
        if run_noon_flag:
            log.info("Waiting %ds before next scraper...", INTER_SCRAPER_DELAY)
            await asyncio.sleep(INTER_SCRAPER_DELAY)

    if run_noon_flag:
        results["noon"] = await run_noon()

    if run_alerts_flag:
        if run_amazon_flag or run_noon_flag:
            await asyncio.sleep(5)  # Brief pause to let DB commits settle
        results["alerts"] = run_alerts()

    total_elapsed = time.time() - total_start
    log.info("\n══════════════════════════════════════════")
    log.info("  Run complete in %.0fs", total_elapsed)
    for component, success in results.items():
        status = "✓" if success else "✗"
        log.info("  %s %s", status, component)
    log.info("══════════════════════════════════════════")

    # Exit with error code if any component failed
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
