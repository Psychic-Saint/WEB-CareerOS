"""
fill_engine/playwright_filler.py

Handles the browser-automation side of applying to a job.

Non-negotiable rules:
  1. Eddie always logs in himself — the script never stores or types passwords.
  2. The script NEVER clicks Submit/Apply. That click is always Eddie's.
  3. A persistent browser profile is used so logins stick between runs.

WHAT'S NEW IN V4:
  - Platform detection: URL is inspected to choose the best adapter
    (Simplify.hr, Greenhouse, Lever, Workday, LinkedIn, generic fallback)
  - Per-platform field selectors: much more accurate than generic guessing
  - CV file auto-attach: if a file upload field is found, your CV is attached
  - apply_to_url(): new entry point — paste ANY job URL and it opens + fills
  - Full-name splitting: adapters needing separate first/last names are handled

FLOW:
  1. Launch a visible Chromium window with a persistent profile.
  2. Detect the ATS platform from the URL.
  3. If the platform needs login: pause, let Eddie log in manually.
  4. Navigate to the apply page, fill text fields, attach CV.
  5. Leave the window open — Eddie reviews, edits, and clicks Submit himself.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright, BrowserContext, Page

from fill_engine.platform_adapters import PLATFORM_ADAPTERS, detect_platform

logger = logging.getLogger("job_pipeline.fill_engine")

# Persistent profile — delete this folder to force a fresh login on all sites.
PROFILE_DIR = Path(__file__).resolve().parent.parent / "browser_profile"
PROFILE_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Browser session management
# ---------------------------------------------------------------------------

def launch_authenticated_session(headless: bool = False) -> tuple[Any, BrowserContext]:
    """
    Launch (or resume) a persistent, visible browser session.
    Returns (playwright_instance, context). Caller closes both when done.
    """
    playwright = sync_playwright().start()
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        args=["--start-maximized"],
    )
    logger.info("Browser launched with persistent profile at %s", PROFILE_DIR)
    return playwright, context


def ensure_logged_in(page: Page, site_url: str, login_check_selector: str) -> None:
    """
    Navigate to site_url. If the login_check_selector is visible, we're
    already logged in. Otherwise, pause and wait for Eddie to log in.
    """
    page.goto(site_url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector(login_check_selector, timeout=4000)
        logger.info("Already logged in to %s", site_url)
        return
    except Exception:
        pass

    print(f"\n{'='*60}")
    print(f"  ACTION NEEDED: Log into {site_url} in the browser window.")
    print(f"  Complete any CAPTCHA or 2FA as needed.")
    print(f"{'='*60}\n")
    input("  Press ENTER once you are logged in...\n")
    logger.info("Continuing after manual login for %s", site_url)


# ---------------------------------------------------------------------------
# Field filling
# ---------------------------------------------------------------------------

def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(" ", 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    return first, last


def fill_with_adapter(
    page: Page,
    adapter: dict[str, Any],
    applicant_data: dict[str, str],
) -> dict[str, str]:
    """
    Fill form fields using the adapter's field_map.
    Returns {field_key: "filled" | "not_found" | "no_data" | "error"}.
    """
    # Derive first/last from full_name if not explicitly supplied
    full_name = applicant_data.get("full_name", "")
    auto_first, auto_last = _split_name(full_name)
    data = {
        "first_name": applicant_data.get("first_name") or auto_first,
        "last_name": applicant_data.get("last_name") or auto_last,
        **applicant_data,
    }

    results: dict[str, str] = {}
    for field_key, selectors in adapter.get("field_map", {}).items():
        value = data.get(field_key)
        if not value:
            results[field_key] = "no_data"
            continue

        filled = False
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0 and locator.is_visible(timeout=1500):
                    locator.click()
                    locator.fill(value)
                    filled = True
                    logger.info("✓ Filled '%s' via %s", field_key, selector)
                    break
            except Exception as exc:
                logger.debug("Selector %s failed for %s: %s", selector, field_key, exc)
                continue
        results[field_key] = "filled" if filled else "not_found"

    return results


def attach_cv(page: Page, adapter: dict[str, Any], cv_path: str | None) -> bool:
    """
    If the adapter defines a CV upload selector and cv_path exists, attach it.
    Returns True if attached successfully.
    """
    selector = adapter.get("cv_upload_selector")
    if not selector or not cv_path:
        return False
    cv = Path(cv_path)
    if not cv.exists():
        logger.warning("CV file not found: %s", cv_path)
        return False
    try:
        file_input = page.locator(selector).first
        if file_input.count() > 0:
            file_input.set_input_files(str(cv))
            logger.info("✓ CV attached from %s", cv_path)
            return True
    except Exception as exc:
        logger.warning("CV attach failed: %s", exc)
    return False


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def apply_to_url(
    url: str,
    applicant_data: dict[str, str],
    cv_path: str | None = None,
    job_title: str = "",
    company: str = "",
) -> dict[str, str]:
    """
    PRIMARY ENTRY POINT — accepts ANY apply URL.

    1. Detects the ATS platform from the URL.
    2. Handles login if required.
    3. Opens the apply page and fills fields using the platform adapter.
    4. Attaches the CV if a file upload field is present.
    5. Leaves the browser open for Eddie to review and submit.

    Returns the fill-results dict so the caller can display what was/wasn't filled.
    """
    platform = detect_platform(url)
    adapter = PLATFORM_ADAPTERS.get(platform, PLATFORM_ADAPTERS["generic"])

    logger.info("Detected platform: %s  (from %s)", platform, url)

    playwright, context = launch_authenticated_session(headless=False)
    page = context.new_page()

    try:
        # Handle login if the platform requires it
        if adapter.get("requires_login") and adapter.get("login_url"):
            ensure_logged_in(
                page,
                adapter["login_url"],
                adapter.get("logged_in_selector", "body"),
            )

        # Navigate to the apply page
        logger.info("Opening: %s", url)
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)  # let React/JS render the form

        # Fill fields
        fill_results = fill_with_adapter(page, adapter, applicant_data)

        # Attach CV
        cv_attached = attach_cv(page, adapter, cv_path)

        # Summary banner
        label = f"{job_title} @ {company}" if job_title or company else url
        filled_count = sum(1 for v in fill_results.values() if v == "filled")
        total_count = sum(1 for v in fill_results.values() if v != "no_data")

        print(f"\n{'='*65}")
        print(f"  ✅  Ready for review: {label}")
        print(f"  Platform  : {platform}")
        print(f"  Fields    : {filled_count}/{total_count} auto-filled")
        print(f"  CV        : {'attached ✓' if cv_attached else 'not attached — please upload manually'}")
        print(f"\n  ⚠️  {adapter.get('post_fill_notes', '')}")
        print(f"\n  The browser is open. Review everything, make any manual edits,")
        print(f"  then click Submit/Apply YOURSELF. The script will not submit.")
        print(f"{'='*65}\n")

        return {**fill_results, "_platform": platform, "_cv_attached": str(cv_attached)}

    except Exception as exc:
        logger.error("apply_to_url failed: %s", exc)
        raise
    finally:
        # Window stays open — intentional. Caller handles cleanup.
        pass


def open_for_review(
    job: dict[str, Any],
    applicant_data: dict[str, str],
    cv_path: str | None = None,
) -> dict[str, str]:
    """
    Entry point for queue-discovered jobs.
    Wraps apply_to_url using the job dict's apply_url, title, and company.
    """
    return apply_to_url(
        url=job["apply_url"],
        applicant_data=applicant_data,
        cv_path=cv_path,
        job_title=job.get("title", ""),
        company=job.get("company", ""),
    )


# ---------------------------------------------------------------------------
# Generic prefill fallback (kept for backward compatibility)
# ---------------------------------------------------------------------------

def prefill_known_fields(page: Page, applicant_data: dict[str, str]) -> dict[str, bool]:
    """
    Legacy generic fill — used if calling code bypasses adapters.
    Kept for backward compat; prefer fill_with_adapter() for new code.
    """
    adapter = PLATFORM_ADAPTERS["generic"]
    results = fill_with_adapter(page, adapter, applicant_data)
    return {k: (v == "filled") for k, v in results.items()}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Usage: python playwright_filler.py <apply_url>")
        print("Example: python playwright_filler.py https://pepkorlifestyle.simplify.hr/Vacancy/Apply/cfa52i")
        sys.exit(1)
    url = sys.argv[1]
    from config.settings import APPLICANT_DATA, CV_PATH
    apply_to_url(url, APPLICANT_DATA, cv_path=CV_PATH or None)
    input("\nPress ENTER to close the browser when you're done...\n")
