#!/usr/bin/env python3
"""
open_jobs.py  — Open all 'approved' jobs in the browser, fill what can
                be filled automatically, then let Eddie review and submit.

Usage:
    python open_jobs.py           # work through all approved jobs one by one
    python open_jobs.py --one     # open only the first approved job
    python open_jobs.py --dry-run # list approved jobs without opening anything

What this does per job:
  1. Opens the apply URL in a persistent browser (same Chrome profile as always).
  2. Detects the ATS platform (Simplify.hr, Greenhouse, Lever, generic, etc.).
  3. Fills text fields with your data from .env / settings.py.
  4. Attaches your CV if the form has a file upload field.
  5. Shows the fill report in the terminal and leaves the browser open.
  6. Asks you: did you submit? → marks job 'submitted' or 'filled' accordingly.

The script NEVER clicks Submit/Apply. That click is always yours.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("open_jobs")


def main() -> None:
    parser = argparse.ArgumentParser(description="Open approved jobs in the browser for filling")
    parser.add_argument("--one",     action="store_true", help="Open only the first approved job")
    parser.add_argument("--dry-run", action="store_true", help="List jobs without opening browser")
    args = parser.parse_args()

    from config.settings import QUEUE_DB_PATH, APPLICANT_DATA, CV_PATH
    from job_queue.store import JobQueueStore
    from fill_engine.playwright_filler import open_for_review

    store   = JobQueueStore(QUEUE_DB_PATH)
    approved = store.get_by_status("approved")

    if not approved:
        print("\n✅  No approved jobs in the queue.")
        print("    Add one with:  python add_job.py <url>")
        print("    Or run the discovery+scoring pipeline to find new jobs.\n")
        return

    jobs = approved[:1] if args.one else approved

    print(f"\n{'='*65}")
    print(f"  {len(jobs)} approved job(s) ready{' (showing 1 of ' + str(len(approved)) + ')' if args.one and len(approved) > 1 else ''}")
    print(f"{'='*65}\n")

    for i, job in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}]  {job['title']}  @  {job['company']}")
        print(f"        {job['apply_url']}\n")

        if args.dry_run:
            continue

        proceed = input("  Open in browser? [Y/n/skip]: ").strip().lower()
        if proceed == "n":
            print("  Stopping here.\n")
            break
        if proceed == "skip":
            store.update_status(job["job_id"], "skipped", notes="Skipped via open_jobs.py")
            print("  → Marked skipped.\n")
            continue

        # ---- Open + fill ----
        try:
            fill_results = open_for_review(
                job,
                APPLICANT_DATA,
                cv_path=CV_PATH or None,
            )
        except Exception as exc:
            logger.error("Fill failed: %s", exc)
            store.update_status(job["job_id"], "failed", notes=str(exc))
            print("  ❌  Fill engine errored — job marked 'failed'. See log above.\n")
            continue

        # Field report
        filled   = [k for k, v in fill_results.items() if v == "filled" and not k.startswith("_")]
        missing  = [k for k, v in fill_results.items() if v == "not_found" and not k.startswith("_")]
        no_data  = [k for k, v in fill_results.items() if v == "no_data" and not k.startswith("_")]

        print(f"\n  Fill report:")
        if filled:   print(f"    ✓ Filled  : {', '.join(filled)}")
        if missing:  print(f"    ✗ Not found (fill manually): {', '.join(missing)}")
        if no_data:  print(f"    – No data : {', '.join(no_data)}  (set in .env to auto-fill)")
        print()

        submitted = input("  Did you successfully submit this application? [y/n]: ").strip().lower()
        if submitted == "y":
            store.update_status(job["job_id"], "submitted",
                                notes="Submitted via open_jobs.py")
            print("  ✅  Marked as submitted!\n")
        else:
            store.update_status(job["job_id"], "filled",
                                notes="Opened but not yet submitted")
            print("  → Marked as 'filled'. Run open_jobs.py again to retry.\n")

    # Final summary
    if not args.dry_run:
        counts = store.counts_by_status()
        print(f"{'='*65}")
        print(f"  Queue: {counts}")
        print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
