"""
Central configuration for Eddie's Job Application Pipeline v5.
All personal data and keys should be in .env — never hardcoded here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

_env_path = BASE_DIR / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ACHIEVEMENT_BANK_PATH = BASE_DIR / "master_achievement_bank.md"
QUEUE_DB_PATH = BASE_DIR / "job_queue" / "job_queue.sqlite3"
LOGS_DIR      = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# AI engines
# ---------------------------------------------------------------------------
DEFAULT_AI_ENGINE  = os.getenv("DEFAULT_AI_ENGINE", "claude")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")

# ---------------------------------------------------------------------------
# Search criteria
# ---------------------------------------------------------------------------
SEARCH_KEYWORDS = [
    "project manager", "project coordinator", "technical project",
    "business analyst", "it support", "support specialist",
    "learning", "l&d", "training coordinator",
    "programme manager", "program manager",
]
PREFERRED_LOCATIONS     = ["Remote", "South Africa", "EMEA", "Worldwide"]
MIN_FIT_SCORE           = int(os.getenv("MIN_FIT_SCORE", "55"))
SEARCH_INTERVAL_MINUTES = int(os.getenv("SEARCH_INTERVAL_MINUTES", "120"))

ENABLED_SOURCES = [
    "remoteok",         # Remote IT/SaaS/BA roles — JSON API
    "jobicy",           # Remote-only curated — JSON API
    "arbeitnow",        # EU-weighted + remote — JSON API
    "weworkremotely",   # High-quality remote roles — RSS
    "workingnomads",    # Curated remote — JSON API
    "himalayas",        # Remote-first companies — JSON API
    "jobspresso",       # Curated remote — RSS
    "remoteco",         # Remote customer support / HR / IT — RSS
]

# ---------------------------------------------------------------------------
# Location policy
# ---------------------------------------------------------------------------
# Remote jobs are always considered globally.
# Onsite jobs are only accepted if the location matches one of these keywords.
ONSITE_LOCATION_KEYWORDS = [
    "johannesburg", "joburg", "jhb", "gauteng", "sandton",
    "midrand", "centurion", "pretoria", "south africa",
]

# ---------------------------------------------------------------------------
# Auto-apply settings
# ---------------------------------------------------------------------------

# If True, the daily runner submits forms automatically on safe platforms.
# Set to False to always escalate everything to Eddie for manual review.
AUTO_SUBMIT_ENABLED = os.getenv("AUTO_SUBMIT_ENABLED", "true").lower() == "true"

# Run the browser headless (invisible) during auto-apply.
# Set to "false" to watch the browser work (useful for debugging).
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

# Generate a per-job cover letter using AI before submitting.
AUTO_COVER_LETTER = os.getenv("AUTO_COVER_LETTER", "true").lower() == "true"

# Max jobs to auto-apply to per daily run (safety limit).
DAILY_AUTO_APPLY_LIMIT = int(os.getenv("DAILY_AUTO_APPLY_LIMIT", "15"))

# Score threshold before auto-applying (separate from MIN_FIT_SCORE which
# controls whether a job enters the queue at all).
AUTO_APPLY_MIN_SCORE = int(os.getenv("AUTO_APPLY_MIN_SCORE", "60"))

# ---------------------------------------------------------------------------
# Your personal data — used to pre-fill application forms
# ---------------------------------------------------------------------------
APPLICANT_DATA: dict[str, str] = {
    "full_name":    os.getenv("APPLICANT_FULL_NAME",  "Eddie Bila"),
    "first_name":   os.getenv("APPLICANT_FIRST_NAME", "Eddie"),
    "last_name":    os.getenv("APPLICANT_LAST_NAME",  "Bila"),
    "email":        os.getenv("APPLICANT_EMAIL",       "eddiebila10@gmail.com"),
    "phone":        os.getenv("APPLICANT_PHONE",       ""),
    "linkedin_url": os.getenv("APPLICANT_LINKEDIN",   ""),
    "id_number":    os.getenv("APPLICANT_ID_NUMBER",  ""),   # keep in .env
    "org":          os.getenv("APPLICANT_ORG",         ""),
}

# Full path to your CV PDF/DOCX
CV_PATH: str = os.getenv("CV_PATH", "")

# ---------------------------------------------------------------------------
# Gmail — for sending email-based applications (apply via email / mailto: links)
# ---------------------------------------------------------------------------
# Set GMAIL_APP_PASSWORD in .env (NOT your real Gmail password).
# Generate an App Password at: https://myaccount.google.com/apppasswords
# (requires 2-Step Verification to be enabled on your Google account)
GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")

# Daily report is saved here (HTML file Eddie can open anytime)
REPORT_PATH = BASE_DIR / "daily_report.html"

# Scheduler — what time the daily run fires (24h format, local time)
DAILY_RUN_TIME = os.getenv("DAILY_RUN_TIME", "07:00")  # 7am
