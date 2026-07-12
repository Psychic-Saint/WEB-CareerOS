#!/usr/bin/env python3
"""
add_job.py  — Add any job URL directly to Eddie's pipeline queue.

Usage:
    python add_job.py <apply_url>
    python add_job.py <apply_url> --title "Head of Academy" --company "SAB"
    python add_job.py <apply_url> --notes "Saw this on LinkedIn, deadline Fri"

The job is inserted with status='approved', bypassing discovery/scoring —
so it goes straight to the fill queue. Run open_jobs.py next to open it.

Examples:
    python add_job.py https://pepkorlifestyle.simplify.hr/Vacancy/Apply/cfa52i
    python add_job.py https://boards.greenhouse.io/acme/jobs/123 --title "PM"
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# Make sure the package root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from job_queue.store import JobQueueStore
from config.settings import QUEUE_DB_PATH
from fill_engine.platform_adapters import detect_platform

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def make_job_id(url: str) -> str:
    return "manual_" + hashlib.sha256(url.encode()).hexdigest()[:12]


def guess_company(url: str) -> str:
    """Best-effort company name from the subdomain or hostname."""
    host = urlparse(url).hostname or ""
    # e.g. "pepkorlifestyle.simplify.hr" → "Pepkorlifestyle"
    # e.g. "boards.greenhouse.io" → keep empty (generic host)
    parts = host.split(".")
    generic_hosts = {"boards", "jobs", "careers", "apply", "hire", "www"}
    for part in parts:
        if part not in generic_hosts and len(part) > 2:
            return part.replace("-", " ").title()
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add any job apply URL to the pipeline queue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("url", help="The full apply URL")
    parser.add_argument("--title",   default="", help="Job title (optional)")
    parser.add_argument("--company", default="", help="Company name (optional)")
    parser.add_argument("--location", default="", help="Location (optional)")
    parser.add_argument("--notes",   default="", help="Notes, e.g. where you saw it")
    args = parser.parse_args()

    url = args.url.strip()
    if not url.startswith("http"):
        print("❌  URL must start with http:// or https://")
        sys.exit(1)

    platform = detect_platform(url)
    company  = args.company or guess_company(url)
    title    = args.title or "Check apply page"

    job = {
        "job_id":      make_job_id(url),
        "source":      "manual",
        "title":       title,
        "company":     company or "Unknown",
        "location":    args.location or "See posting",
        "is_remote":   False,
        "description": "",
        "tags":        ["manual", platform],
        "apply_url":   url,
        "posted_at":   datetime.now(timezone.utc).isoformat(),
        "salary_text": None,
    }

    store = JobQueueStore(QUEUE_DB_PATH)
    inserted = store.upsert_job(job)

    if not inserted:
        print(f"⚠️  Job already in queue (URL matched existing entry).")
        print(f"    Updating status to 'approved' so it re-enters the fill queue...")
    else:
        print(f"✅  Job added!")

    store.update_status(
        job["job_id"],
        "approved",
        notes=(args.notes or f"Manually added {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"),
    )

    print()
    print(f"  Title    : {title}")
    print(f"  Company  : {company or 'Unknown (edit with --company)'}")
    print(f"  Platform : {platform}")
    print(f"  URL      : {url}")
    print(f"  Status   : approved  ← ready for fill engine")
    print()
    print("Next step:")
    print("  python open_jobs.py")
    print()


if __name__ == "__main__":
    main()
