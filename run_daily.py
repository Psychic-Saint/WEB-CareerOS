#!/usr/bin/env python3
"""
run_daily.py  — The full automated pipeline. Run this once to start it;
                it then fires every day at the time set in DAILY_RUN_TIME.

What it does each cycle:
  1. Discovers new jobs from 8 sources:
       RemoteOK, Jobicy, Arbeitnow, We Work Remotely,
       Working Nomads, Himalayas, Jobspresso, Remote.co
     Location policy: remote jobs = global  |  onsite = Joburg/Gauteng only.
  2. Scores each job against your CV with Claude/Gemini.
  3. Discards jobs below MIN_FIT_SCORE.
  4. For jobs above AUTO_APPLY_MIN_SCORE → attempts auto-apply:
       - Form-based jobs  → Playwright fills + submits the form
       - mailto: links    → Gmail SMTP sends your CV via eddiebila10@gmail.com
       - Workday/LinkedIn → always escalated to you
  5. Submitted applications → status = "submitted".
  6. Escalated (CAPTCHA / manual platform / low fill rate) → status = "escalated".
  7. Writes a daily HTML report to daily_report.html.

Usage:
  python run_daily.py            # start the scheduler (runs until you Ctrl+C)
  python run_daily.py --now      # run one cycle immediately, then exit
  python run_daily.py --discover # discover + score only (no applying)
  python run_daily.py --apply    # apply only (skip discovery/scoring)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("run_daily")


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def step_discover(store, settings) -> int:
    """Fetch new jobs from all enabled sources, save to queue."""
    from discovery.sources import fetch_all_sources
    logger.info("=== DISCOVERY ===")
    jobs = fetch_all_sources(
        enabled_sources=settings.ENABLED_SOURCES,
        keywords=settings.SEARCH_KEYWORDS,
    )
    new_count = 0
    for job in jobs:
        job_dict = job.__dict__ if hasattr(job, "__dict__") else dict(job)
        if store.upsert_job(job_dict):
            new_count += 1
    logger.info("Discovered %d total, %d new", len(jobs), new_count)
    return new_count


def step_score(store, settings, cv_text: str) -> int:
    """Score all 'new' jobs. Discard below MIN_FIT_SCORE."""
    from ai.scorer import score_job
    logger.info("=== SCORING ===")
    new_jobs = store.get_by_status("new")
    if not new_jobs:
        logger.info("No new jobs to score")
        return 0

    scored = 0
    for job in new_jobs:
        score, reasoning, gaps = score_job(
            job, cv_text,
            engine=settings.DEFAULT_AI_ENGINE,
            anthropic_key=settings.ANTHROPIC_API_KEY,
            gemini_key=settings.GEMINI_API_KEY,
        )
        store.set_score(job["job_id"], score, reasoning, gaps)

        if score >= settings.MIN_FIT_SCORE:
            # Mark ready for apply queue
            store.update_status(job["job_id"], "approved",
                                notes=f"Score {score}: {reasoning[:80]}")
            logger.info("✓ %s @ %s  score=%d  → approved", job["title"], job["company"], score)
        else:
            store.update_status(job["job_id"], "rejected",
                                notes=f"Score {score} below threshold {settings.MIN_FIT_SCORE}")
            logger.info("✗ %s @ %s  score=%d  → rejected", job["title"], job["company"], score)
        scored += 1
    return scored


def step_apply(store, settings, cv_text: str) -> dict:
    """Auto-apply to all approved jobs within daily limit."""
    if not settings.AUTO_SUBMIT_ENABLED:
        logger.info("AUTO_SUBMIT_ENABLED=false — skipping auto-apply")
        return {"submitted": 0, "escalated": 0, "failed": 0}

    from fill_engine.auto_apply import attempt_auto_apply
    from ai.scorer import generate_cover_letter

    logger.info("=== AUTO-APPLY ===")
    approved = store.get_by_status("approved", min_fit_score=settings.AUTO_APPLY_MIN_SCORE)

    if not approved:
        logger.info("No approved jobs ready")
        return {"submitted": 0, "escalated": 0, "failed": 0}

    approved = approved[:settings.DAILY_AUTO_APPLY_LIMIT]
    logger.info("%d job(s) to attempt", len(approved))

    counts = {"submitted": 0, "escalated": 0, "failed": 0}

    for job in approved:
        cover_letter = ""
        if settings.AUTO_COVER_LETTER and cv_text:
            cover_letter = generate_cover_letter(
                job, cv_text,
                engine=settings.DEFAULT_AI_ENGINE,
                anthropic_key=settings.ANTHROPIC_API_KEY,
                gemini_key=settings.GEMINI_API_KEY,
            )

        result = attempt_auto_apply(
            job=job,
            applicant_data=settings.APPLICANT_DATA,
            cv_path=settings.CV_PATH or None,
            cover_letter_text=cover_letter,
            headless=settings.HEADLESS,
        )

        note = f"platform={result.platform} | {result.reason}" if result.reason else f"platform={result.platform}"
        store.update_status(job["job_id"], result.status, notes=note)
        if result.screenshot_path:
            store.set_screenshot(job["job_id"], result.screenshot_path)

        counts[result.status] = counts.get(result.status, 0) + 1
        logger.info("%s → %s  (%s)", job["title"], result.status, result.reason or "ok")

        time.sleep(3)   # polite pause between applications

    return counts


def step_report(store, settings, counts: dict, run_start: datetime) -> None:
    """Write a daily HTML report."""
    from app.report import write_html_report
    write_html_report(store, settings, counts, run_start)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_cycle(args) -> None:
    import config.settings as settings
    from job_queue.store import JobQueueStore
    from ai.scorer import load_cv_text

    store = JobQueueStore(settings.QUEUE_DB_PATH)
    cv_text = load_cv_text(settings.CV_PATH) if settings.CV_PATH else ""

    if not cv_text:
        logger.warning("⚠️  CV text could not be loaded from CV_PATH — scoring will be skipped")

    run_start = datetime.now()
    counts = {"submitted": 0, "escalated": 0, "failed": 0}

    if not args.apply_only:
        step_discover(store, settings)
        step_score(store, settings, cv_text)

    if not args.discover_only:
        counts = step_apply(store, settings, cv_text)

    step_report(store, settings, counts, run_start)

    queue = store.counts_by_status()
    escalated_count = queue.get("escalated", 0)

    print(f"\n{'='*60}")
    print(f"  Run complete — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Submitted : {counts.get('submitted', 0)}")
    print(f"  Escalated : {counts.get('escalated', 0)}  ← open review_app.py")
    print(f"  Failed    : {counts.get('failed', 0)}")
    print(f"  Queue     : {queue}")
    if escalated_count:
        print(f"\n  ⚠️  {escalated_count} job(s) need your attention.")
        print(f"      Run:  streamlit run app/review_app.py")
    print(f"  Report    : {settings.REPORT_PATH}")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Eddie's Job Pipeline — daily runner")
    parser.add_argument("--now",          action="store_true", dest="run_now",
                        help="Run one cycle immediately, then exit")
    parser.add_argument("--discover",     action="store_true", dest="discover_only",
                        help="Discover + score only (no applying)")
    parser.add_argument("--apply",        action="store_true", dest="apply_only",
                        help="Apply only (skip discover/score)")
    parser.add_argument("--once",         action="store_true",
                        help="Same as --now")
    args = parser.parse_args()

    if args.run_now or args.once or args.discover_only or args.apply_only:
        run_cycle(args)
        return

    # Scheduled mode
    import config.settings as settings
    from apscheduler.schedulers.blocking import BlockingScheduler

    hour, minute = (int(x) for x in settings.DAILY_RUN_TIME.split(":"))
    scheduler = BlockingScheduler(timezone="Africa/Johannesburg")
    scheduler.add_job(
        lambda: run_cycle(args),
        trigger="cron",
        hour=hour,
        minute=minute,
        id="daily_apply",
    )

    print(f"\n✅  Scheduler started — runs daily at {settings.DAILY_RUN_TIME} (SAST)")
    print(f"    Press Ctrl+C to stop.\n")

    # Run once immediately on start
    print("Running initial cycle now...")
    run_cycle(args)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")


if __name__ == "__main__":
    main()
