"""
discovery/sources.py

Pulls raw job postings from free, no-key job board APIs and normalises
them into a single shape so the rest of the pipeline doesn't care which
source a job came from.

Live endpoints (verified June 2026):
  - RemoteOK      : https://remoteok.com/api                          (JSON)
  - Arbeitnow     : https://arbeitnow.com/api/job-board-api           (JSON)
  - Jobicy        : https://jobicy.com/api/v2/remote-jobs             (JSON)
  - We Work Remotely : https://weworkremotely.com/remote-jobs.rss     (RSS)
  - Working Nomads: https://www.workingnomads.com/api/exposed_jobs/   (JSON)
  - Himalayas     : https://himalayas.app/api/jobs                    (JSON)
  - Jobspresso    : https://jobspresso.co/remote-work/feed/           (RSS)
  - Remote.co     : https://remote.co/remote-jobs/feed/              (RSS)

LOCATION POLICY (enforced before anything enters the queue):
  - Remote jobs   → accepted globally
  - Onsite jobs   → only accepted if location is in/near Johannesburg, SA
"""

from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, parse_qs

import requests

logger = logging.getLogger("job_pipeline.discovery")

USER_AGENT = "EddieBila-PersonalJobPipeline/1.0 (+personal use, not a bulk scraper)"
TIMEOUT_SECONDS = 15

# ---------------------------------------------------------------------------
# Location policy — onsite roles must be in/near Johannesburg
# ---------------------------------------------------------------------------
_JOBURG_KEYWORDS = {
    "johannesburg", "joburg", "jhb", "gauteng", "sandton",
    "midrand", "centurion", "pretoria", "south africa", "za",
}

def _location_allowed(location: str, is_remote: bool) -> bool:
    """Remote jobs are allowed globally. Onsite = Joburg/Gauteng only."""
    if is_remote:
        return True
    loc_lower = location.lower()
    return any(kw in loc_lower for kw in _JOBURG_KEYWORDS)


# ---------------------------------------------------------------------------
# Normalised job shape
# ---------------------------------------------------------------------------

@dataclass
class NormalizedJob:
    """A single job posting, normalised across all sources."""
    job_id:      str        # stable hash for de-duplication
    source:      str        # "remoteok" | "arbeitnow" | ...
    title:       str
    company:     str
    location:    str
    is_remote:   bool
    description: str
    tags:        list[str]
    apply_url:   str        # NEVER rewritten/shortened
    posted_at:   str        # ISO 8601
    salary_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _make_job_id(source: str, title: str, company: str, apply_url: str) -> str:
    raw = f"{source}|{title}|{company}|{apply_url}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# RSS helper — parses any standard RSS 2.0 feed without extra deps
# ---------------------------------------------------------------------------

def _parse_rss_items(xml_bytes: bytes) -> list[dict]:
    """Return list of {title, link, description, pubDate} from an RSS feed."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning("RSS parse error: %s", e)
        return []

    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
    items = []
    for item in root.findall(".//item"):
        # <link> is sometimes a text node, sometimes a CDATA
        link_el = item.find("link")
        link = (link_el.text or "").strip() if link_el is not None else ""
        # Some feeds put the real URL as the next text sibling
        if not link:
            link = item.findtext("{http://www.w3.org/2005/Atom}link", "")

        raw_desc = item.findtext("description", "") or ""
        # Strip HTML tags from description for plain text
        import re
        clean_desc = re.sub(r"<[^>]+>", " ", raw_desc).strip()

        items.append({
            "title":       (item.findtext("title") or "").strip(),
            "link":        link,
            "description": clean_desc[:500],
            "pubDate":     item.findtext("pubDate", ""),
            "region":      item.findtext("region", ""),  # WeWorkRemotely uses this
        })
    return items


# ---------------------------------------------------------------------------
# Source 1 — RemoteOK
# ---------------------------------------------------------------------------

def fetch_remoteok(keywords: list[str]) -> list[NormalizedJob]:
    url     = "https://remoteok.com/api"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        raw_jobs = resp.json()
    except requests.RequestException as e:
        logger.warning("RemoteOK fetch failed: %s", e)
        return []

    if not raw_jobs or not isinstance(raw_jobs, list):
        return []

    postings = raw_jobs[1:]   # first element is metadata
    results: list[NormalizedJob] = []
    kw_lower = [k.lower() for k in keywords]

    for job in postings:
        title = job.get("position") or job.get("title") or ""
        if not title:
            continue
        title_lower = title.lower()
        tags_lower  = " ".join(job.get("tags", []) or []).lower().replace("-", " ")
        if kw_lower and not (
            any(k in title_lower for k in kw_lower) or
            any(k in tags_lower  for k in kw_lower)
        ):
            continue

        apply_url = job.get("apply_url") or job.get("url", "")
        company   = job.get("company", "Unknown")

        results.append(NormalizedJob(
            job_id=_make_job_id("remoteok", title, company, apply_url),
            source="remoteok",
            title=title,
            company=company,
            location="Remote",
            is_remote=True,
            description=job.get("description", "") or "",
            tags=job.get("tags", []) or [],
            apply_url=apply_url,
            posted_at=job.get("date", datetime.now(timezone.utc).isoformat()),
            salary_text=_format_salary(job.get("salary_min"), job.get("salary_max")),
        ))

    logger.info("RemoteOK: %d matching", len(results))
    return results


# ---------------------------------------------------------------------------
# Source 2 — Arbeitnow
# ---------------------------------------------------------------------------

def fetch_arbeitnow(keywords: list[str]) -> list[NormalizedJob]:
    url     = "https://arbeitnow.com/api/job-board-api"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as e:
        logger.warning("Arbeitnow fetch failed: %s", e)
        return []

    postings  = payload.get("data", [])
    results   = []
    kw_lower  = [k.lower() for k in keywords]

    for job in postings:
        title = job.get("title", "")
        if not title:
            continue
        if kw_lower and not any(k in title.lower() for k in kw_lower):
            continue

        is_remote = bool(job.get("remote", False))
        location  = job.get("location", "") or "Not specified"
        if not _location_allowed(location, is_remote):
            continue

        apply_url = job.get("url", "")
        company   = job.get("company_name", "Unknown")

        results.append(NormalizedJob(
            job_id=_make_job_id("arbeitnow", title, company, apply_url),
            source="arbeitnow",
            title=title,
            company=company,
            location=location,
            is_remote=is_remote,
            description=job.get("description", "") or "",
            tags=job.get("tags", []) or [],
            apply_url=apply_url,
            posted_at=datetime.fromtimestamp(
                job.get("created_at", 0), tz=timezone.utc
            ).isoformat() if job.get("created_at") else "",
        ))

    logger.info("Arbeitnow: %d matching", len(results))
    return results


# ---------------------------------------------------------------------------
# Source 3 — Jobicy
# ---------------------------------------------------------------------------

def fetch_jobicy(keywords: list[str]) -> list[NormalizedJob]:
    url     = "https://jobicy.com/api/v2/remote-jobs"
    params  = {"count": 50}
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as e:
        logger.warning("Jobicy fetch failed: %s", e)
        return []

    postings = payload.get("jobs", [])
    results  = []
    kw_lower = [k.lower() for k in keywords]

    for job in postings:
        title = job.get("jobTitle", "")
        if not title:
            continue

        industry_raw = job.get("jobIndustry", "") or ""
        if isinstance(industry_raw, list):
            industry_raw = " ".join(industry_raw)
        industry_lower = industry_raw.lower()

        if kw_lower and not (
            any(k in title.lower()    for k in kw_lower) or
            any(k in industry_lower   for k in kw_lower)
        ):
            continue

        apply_url = job.get("url", "")
        company   = job.get("companyName", "Unknown")

        results.append(NormalizedJob(
            job_id=_make_job_id("jobicy", title, company, apply_url),
            source="jobicy",
            title=title,
            company=company,
            location=job.get("jobGeo", "Anywhere") or "Anywhere",
            is_remote=True,
            description=job.get("jobExcerpt", "") or "",
            tags=[industry_raw] if industry_raw else [],
            apply_url=apply_url,
            posted_at=job.get("pubDate", ""),
            salary_text=_format_salary(job.get("annualSalaryMin"), job.get("annualSalaryMax")),
        ))

    logger.info("Jobicy: %d matching", len(results))
    return results


# ---------------------------------------------------------------------------
# Source 4 — We Work Remotely (RSS)
# ---------------------------------------------------------------------------

def fetch_weworkremotely(keywords: list[str]) -> list[NormalizedJob]:
    """
    We Work Remotely publishes a public RSS feed.
    Title format: "[Category] Job Title at Company Name"
    """
    url     = "https://weworkremotely.com/remote-jobs.rss"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("WeWorkRemotely fetch failed: %s", e)
        return []

    items    = _parse_rss_items(resp.content)
    results  = []
    kw_lower = [k.lower() for k in keywords]

    for item in items:
        raw_title = item["title"]
        # Title often: "[Design] UX Lead at Acme Corp"
        # Strip category bracket if present
        import re
        category_match = re.match(r"^\[([^\]]+)\]\s*", raw_title)
        category = category_match.group(1) if category_match else ""
        clean_title = re.sub(r"^\[[^\]]+\]\s*", "", raw_title).strip()

        # Extract company from "Job Title at Company Name"
        if " at " in clean_title:
            parts   = clean_title.rsplit(" at ", 1)
            title   = parts[0].strip()
            company = parts[1].strip()
        else:
            title   = clean_title
            company = "Unknown"

        if not title:
            continue

        search_text = f"{title} {category}".lower()
        if kw_lower and not any(k in search_text for k in kw_lower):
            continue

        link = item["link"]
        # WWR links point to listing pages — these are always remote
        results.append(NormalizedJob(
            job_id=_make_job_id("weworkremotely", title, company, link),
            source="weworkremotely",
            title=title,
            company=company,
            location="Remote",
            is_remote=True,
            description=item["description"],
            tags=[category] if category else [],
            apply_url=link,
            posted_at=item["pubDate"],
        ))

    logger.info("WeWorkRemotely: %d matching", len(results))
    return results


# ---------------------------------------------------------------------------
# Source 5 — Working Nomads (REST API, no key required)
# ---------------------------------------------------------------------------

def fetch_workingnomads(keywords: list[str]) -> list[NormalizedJob]:
    url     = "https://www.workingnomads.com/api/exposed_jobs/"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        postings = resp.json()
    except requests.RequestException as e:
        logger.warning("WorkingNomads fetch failed: %s", e)
        return []

    if not isinstance(postings, list):
        return []

    results  = []
    kw_lower = [k.lower() for k in keywords]

    for job in postings:
        title   = (job.get("title") or "").strip()
        company = (job.get("company_name") or "Unknown").strip()
        if not title:
            continue

        tags_str = " ".join(job.get("tags", []) or []).lower()
        if kw_lower and not (
            any(k in title.lower() for k in kw_lower) or
            any(k in tags_str      for k in kw_lower)
        ):
            continue

        apply_url = job.get("url") or job.get("apply_url", "")
        location  = job.get("location", "Remote") or "Remote"
        # Working Nomads is remote-first
        is_remote = True

        results.append(NormalizedJob(
            job_id=_make_job_id("workingnomads", title, company, apply_url),
            source="workingnomads",
            title=title,
            company=company,
            location=location,
            is_remote=is_remote,
            description=job.get("description", "") or "",
            tags=job.get("tags", []) or [],
            apply_url=apply_url,
            posted_at=job.get("pub_date_iso", ""),
            salary_text=job.get("salary") or None,
        ))

    logger.info("WorkingNomads: %d matching", len(results))
    return results


# ---------------------------------------------------------------------------
# Source 6 — Himalayas (REST API, no key required)
# ---------------------------------------------------------------------------

def fetch_himalayas(keywords: list[str]) -> list[NormalizedJob]:
    """
    Himalayas.app has a clean public API returning JSON job listings.
    Supports pagination — we pull up to 2 pages (100 jobs each).
    """
    base_url = "https://himalayas.app/api/jobs"
    headers  = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    results  = []
    kw_lower = [k.lower() for k in keywords]

    for page in range(1, 3):  # pages 1 and 2
        try:
            resp = requests.get(
                base_url,
                params={"limit": 100, "page": page},
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as e:
            logger.warning("Himalayas fetch failed (page %d): %s", page, e)
            break

        postings = payload.get("jobs", [])
        if not postings:
            break

        for job in postings:
            title   = (job.get("title") or "").strip()
            company = (job.get("company", {}) or {}).get("name", "Unknown")
            if not title:
                continue

            cats_str = " ".join(job.get("categories", []) or []).lower()
            if kw_lower and not (
                any(k in title.lower() for k in kw_lower) or
                any(k in cats_str      for k in kw_lower)
            ):
                continue

            apply_url = job.get("applicationUrl") or job.get("url", "")
            location  = job.get("location", "Remote") or "Remote"
            is_remote = bool(job.get("isRemote", True))

            if not _location_allowed(location, is_remote):
                continue

            results.append(NormalizedJob(
                job_id=_make_job_id("himalayas", title, company, apply_url),
                source="himalayas",
                title=title,
                company=company,
                location=location,
                is_remote=is_remote,
                description=job.get("description", "") or "",
                tags=job.get("categories", []) or [],
                apply_url=apply_url,
                posted_at=job.get("publishedAt", ""),
            ))

    logger.info("Himalayas: %d matching", len(results))
    return results


# ---------------------------------------------------------------------------
# Source 7 — Jobspresso (WordPress RSS)
# ---------------------------------------------------------------------------

def fetch_jobspresso(keywords: list[str]) -> list[NormalizedJob]:
    url     = "https://jobspresso.co/remote-work/feed/"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Jobspresso fetch failed: %s", e)
        return []

    items    = _parse_rss_items(resp.content)
    results  = []
    kw_lower = [k.lower() for k in keywords]

    for item in items:
        title = item["title"].strip()
        if not title:
            continue
        if kw_lower and not any(k in title.lower() for k in kw_lower):
            continue

        link = item["link"]
        # Jobspresso titles sometimes include "– Company" at end
        company = "Unknown"
        if " – " in title:
            parts   = title.rsplit(" – ", 1)
            title   = parts[0].strip()
            company = parts[1].strip()
        elif " - " in title:
            parts   = title.rsplit(" - ", 1)
            title   = parts[0].strip()
            company = parts[1].strip()

        results.append(NormalizedJob(
            job_id=_make_job_id("jobspresso", title, company, link),
            source="jobspresso",
            title=title,
            company=company,
            location="Remote",
            is_remote=True,
            description=item["description"],
            tags=[],
            apply_url=link,
            posted_at=item["pubDate"],
        ))

    logger.info("Jobspresso: %d matching", len(results))
    return results


# ---------------------------------------------------------------------------
# Source 8 — Remote.co (WordPress RSS)
# ---------------------------------------------------------------------------

def fetch_remoteco(keywords: list[str]) -> list[NormalizedJob]:
    url     = "https://remote.co/remote-jobs/feed/"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Remote.co fetch failed: %s", e)
        return []

    items    = _parse_rss_items(resp.content)
    results  = []
    kw_lower = [k.lower() for k in keywords]

    for item in items:
        title = item["title"].strip()
        if not title:
            continue
        if kw_lower and not any(k in title.lower() for k in kw_lower):
            continue

        link    = item["link"]
        company = "Unknown"
        if " at " in title:
            parts   = title.rsplit(" at ", 1)
            title   = parts[0].strip()
            company = parts[1].strip()

        results.append(NormalizedJob(
            job_id=_make_job_id("remoteco", title, company, link),
            source="remoteco",
            title=title,
            company=company,
            location="Remote",
            is_remote=True,
            description=item["description"],
            tags=[],
            apply_url=link,
            posted_at=item["pubDate"],
        ))

    logger.info("Remote.co: %d matching", len(results))
    return results


# ---------------------------------------------------------------------------
# Shared salary formatter
# ---------------------------------------------------------------------------

def _format_salary(salary_min, salary_max) -> str | None:
    if not salary_min and not salary_max:
        return None
    if salary_min and salary_max:
        return f"${int(salary_min):,} – ${int(salary_max):,}"
    return f"${int(salary_min or salary_max):,}"


# ---------------------------------------------------------------------------
# Source registry — add new sources here as they're verified working.
# ---------------------------------------------------------------------------
SOURCE_FETCHERS = {
    "remoteok":       fetch_remoteok,
    "arbeitnow":      fetch_arbeitnow,
    "jobicy":         fetch_jobicy,
    "weworkremotely": fetch_weworkremotely,
    "workingnomads":  fetch_workingnomads,
    "himalayas":      fetch_himalayas,
    "jobspresso":     fetch_jobspresso,
    "remoteco":       fetch_remoteco,
}


def fetch_all_sources(enabled_sources: list[str], keywords: list[str]) -> list[NormalizedJob]:
    """Run every enabled source fetcher and return a combined, de-duplicated list."""
    all_jobs: list[NormalizedJob] = []
    seen_ids: set[str] = set()

    for source_name in enabled_sources:
        fetcher = SOURCE_FETCHERS.get(source_name)
        if not fetcher:
            logger.warning("Unknown source '%s' — skipping.", source_name)
            continue
        try:
            jobs = fetcher(keywords)
        except Exception as exc:
            logger.error("Source '%s' raised an exception: %s", source_name, exc, exc_info=True)
            jobs = []

        for job in jobs:
            if job.job_id not in seen_ids:
                seen_ids.add(job.job_id)
                all_jobs.append(job)

    logger.info("Total unique jobs across all sources: %d", len(all_jobs))
    return all_jobs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    kws  = ["project manager", "business analyst", "it support", "programme manager"]
    jobs = fetch_all_sources(list(SOURCE_FETCHERS.keys()), kws)
    print(f"\nTotal unique jobs: {len(jobs)}\n")
    by_source: dict[str, int] = {}
    for j in jobs:
        by_source[j.source] = by_source.get(j.source, 0) + 1
    for src, cnt in sorted(by_source.items()):
        print(f"  {src:20s} {cnt}")
    print()
    for j in jobs[:5]:
        print(f"  [{j.source}] {j.title} @ {j.company}")
        print(f"  Apply: {j.apply_url}\n")
