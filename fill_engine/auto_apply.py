"""
fill_engine/auto_apply.py  — The core auto-submit engine.

WHAT IT DOES:
  For each job in the 'approved' queue:
    1. Opens the apply URL in a persistent browser (optionally headless).
    2. Detects the ATS platform.
    3. Fills every text field it can (name, email, phone, LinkedIn, ID, etc.).
    4. Attaches the CV to the file upload field.
    5. Injects a cover letter into any cover-letter text area (if provided).
    6. Checks whether the platform is safe to auto-submit:
         - Platform is marked auto_submit_safe = True
         - No CAPTCHA detected
         - Fill rate >= adapter's escalation_threshold
         - Submit button found
    7a. If all checks pass → clicks Submit → verifies success → status = "submitted"
    7b. If any check fails → takes screenshot → status = "escalated"
           Eddie sees it in the Streamlit review app.

WHAT IT NEVER DOES:
  - Store or type passwords
  - Skip escalation checks
  - Retry a submission that already succeeded

CAPTCHA handling:
  Detects reCAPTCHA and hCaptcha iframes. When found, escalates immediately.
  If you want to pay for a captcha-solving service (2captcha etc.) in future,
  the hook is in _check_captcha() — replace the escalate with a solve call.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright, Page, BrowserContext

from fill_engine.platform_adapters import PLATFORM_ADAPTERS, detect_platform

logger = logging.getLogger("job_pipeline.auto_apply")

PROFILE_DIR = Path(__file__).resolve().parent.parent / "browser_profile"
PROFILE_DIR.mkdir(exist_ok=True)

SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AutoApplyResult:
    status: str                        # "submitted" | "escalated" | "failed"
    reason: str = ""                   # why it was escalated/failed
    fill_results: dict = field(default_factory=dict)
    cv_attached: bool = False
    cover_letter_injected: bool = False
    screenshot_path: str = ""
    platform: str = "generic"


# ---------------------------------------------------------------------------
# CAPTCHA detection
# ---------------------------------------------------------------------------

CAPTCHA_SELECTORS = [
    'iframe[src*="recaptcha"]',
    'iframe[src*="hcaptcha"]',
    'iframe[title*="captcha" i]',
    '[class*="captcha" i]',
    '[id*="captcha" i]',
    'iframe[src*="turnstile"]',   # Cloudflare Turnstile
]


def _check_captcha(page: Page) -> bool:
    """Return True if a CAPTCHA is visible on the page."""
    for sel in CAPTCHA_SELECTORS:
        try:
            if page.locator(sel).count() > 0:
                logger.warning("CAPTCHA detected: %s", sel)
                return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Field filling
# ---------------------------------------------------------------------------

def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(" ", 1)
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")


def _click_apply_button(page: Page) -> None:
    """
    Many job listing pages hide the application form behind an 'Apply' button.
    This function tries to click through to the form before we attempt to fill fields.
    If no Apply button is found, or we're already on a form page, this is a no-op.
    """
    # Only click if there are no visible text input fields yet (i.e. we're on a listing page)
    try:
        visible_inputs = page.locator(
            'input[type="text"], input[type="email"], input[type="tel"]'
        ).count()
        if visible_inputs >= 2:
            return   # Already on a form page — don't need to click Apply
    except Exception:
        pass

    apply_selectors = [
        'a:has-text("Apply Now")',
        'a:has-text("Apply for this Job")',
        'a:has-text("Apply for this job")',
        'a:has-text("Apply")',
        'button:has-text("Apply Now")',
        'button:has-text("Apply for this Job")',
        'button:has-text("Apply")',
        '[data-qa="btn-apply"]',
        '.apply-button',
        '#apply-button',
        'a[href*="/apply"]',
    ]
    for sel in apply_selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=1000):
                loc.click()
                page.wait_for_timeout(3000)   # wait for form/redirect
                logger.info("Clicked Apply button via: %s", sel)
                break
        except Exception:
            continue


def _fill_fields(page: Page, adapter: dict, applicant_data: dict) -> dict[str, str]:
    """Fill form fields. Returns {field_key: status}."""
    full = applicant_data.get("full_name", "")
    auto_first, auto_last = _split_name(full)
    data = {
        "first_name": applicant_data.get("first_name") or auto_first,
        "last_name":  applicant_data.get("last_name")  or auto_last,
        **applicant_data,
    }
    results: dict[str, str] = {}
    for key, selectors in adapter.get("field_map", {}).items():
        value = data.get(key)
        if not value:
            results[key] = "no_data"
            continue
        filled = False
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=1500):
                    loc.click()
                    loc.fill(value)
                    filled = True
                    logger.debug("✓ %s via %s", key, sel)
                    break
            except Exception:
                continue
        results[key] = "filled" if filled else "not_found"
    return results


def _attach_cv(page: Page, adapter: dict, cv_path: str | None) -> bool:
    sel = adapter.get("cv_upload_selector")
    if not sel or not cv_path:
        return False
    cv = Path(cv_path)
    if not cv.exists():
        logger.warning("CV not found: %s", cv_path)
        return False
    try:
        fi = page.locator(sel).first
        if fi.count() > 0:
            fi.set_input_files(str(cv))
            logger.info("✓ CV attached")
            return True
    except Exception as e:
        logger.warning("CV attach failed: %s", e)
    return False


def _inject_cover_letter(page: Page, cover_letter_text: str) -> bool:
    """Try to fill any visible cover letter textarea."""
    if not cover_letter_text:
        return False
    selectors = [
        'textarea[name*="cover" i]',
        'textarea[id*="cover" i]',
        'textarea[placeholder*="cover letter" i]',
        'textarea[placeholder*="motivation" i]',
        'textarea[aria-label*="cover letter" i]',
        'textarea[name*="letter" i]',
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=1500):
                loc.fill(cover_letter_text)
                logger.info("✓ Cover letter injected")
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Consent/terms checkbox handling
# ---------------------------------------------------------------------------

def _tick_consent_checkboxes(page: Page) -> None:
    """Auto-tick privacy/terms consent checkboxes if present."""
    consent_selectors = [
        'input[type="checkbox"][name*="consent" i]',
        'input[type="checkbox"][name*="privacy" i]',
        'input[type="checkbox"][name*="terms" i]',
        'input[type="checkbox"][name*="gdpr" i]',
        'input[type="checkbox"][id*="consent" i]',
        'input[type="checkbox"][id*="privacy" i]',
        'input[type="checkbox"][id*="terms" i]',
    ]
    for sel in consent_selectors:
        try:
            boxes = page.locator(sel)
            for i in range(boxes.count()):
                box = boxes.nth(i)
                if box.is_visible() and not box.is_checked():
                    box.check()
                    logger.debug("✓ Checked consent box: %s", sel)
        except Exception:
            continue


# ---------------------------------------------------------------------------
# Success detection
# ---------------------------------------------------------------------------

def _detect_success(page: Page, adapter: dict) -> bool:
    try:
        body_text = page.inner_text("body").lower()
        for pattern in adapter.get("success_patterns", []):
            if pattern in body_text:
                return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def _screenshot(page: Page, job_id: str, suffix: str = "") -> str:
    filename = f"{job_id}_{suffix}_{int(time.time())}.png"
    path = SCREENSHOTS_DIR / filename
    try:
        page.screenshot(path=str(path), full_page=False)
        return str(path)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Core: attempt_auto_apply
# ---------------------------------------------------------------------------

def attempt_auto_apply(
    job: dict[str, Any],
    applicant_data: dict[str, str],
    cv_path: str | None = None,
    cover_letter_text: str = "",
    headless: bool = True,
) -> AutoApplyResult:
    """
    Main entry point.  Tries to auto-apply to job['apply_url'].
    Returns an AutoApplyResult — caller updates the queue status.

    headless=True for scheduled overnight runs.
    headless=False for Streamlit-triggered manual-assist mode (Eddie watches).
    """
    url      = job["apply_url"]
    job_id   = job.get("job_id", "unknown")

    # ---- mailto: links → send via Gmail, skip the browser entirely ----
    if url.startswith("mailto:"):
        from fill_engine.gmail_sender import send_email_application
        import os
        from_email   = applicant_data.get("email", "")
        app_password = os.getenv("GMAIL_APP_PASSWORD", "")
        success, reason = send_email_application(
            job=job,
            apply_url=url,
            applicant_data=applicant_data,
            cv_path=cv_path,
            cover_letter_text=cover_letter_text,
            from_email=from_email,
            app_password=app_password,
        )
        return AutoApplyResult(
            status="submitted" if success else "escalated",
            reason=reason,
            platform="email",
        )

    platform = detect_platform(url)
    adapter  = PLATFORM_ADAPTERS.get(platform, PLATFORM_ADAPTERS["generic"])

    logger.info("auto_apply: %s @ %s  [%s]", job.get("title"), job.get("company"), platform)

    result = AutoApplyResult(status="escalated", platform=platform)

    playwright = sync_playwright().start()
    try:
        context: BrowserContext = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        # ---- Navigate ----
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2500)   # JS render time

        # ---- CAPTCHA check ----
        if _check_captcha(page):
            result.screenshot_path = _screenshot(page, job_id, "captcha")
            result.status = "escalated"
            result.reason = "captcha_detected"
            return result

        # ---- Click "Apply" button if form not yet visible ----
        # Job listing pages often show the form only after clicking Apply/Apply Now.
        # Try to click through to the form before attempting to fill fields.
        _click_apply_button(page)

        # ---- Fill fields ----
        fill_res = _fill_fields(page, adapter, applicant_data)
        result.fill_results = fill_res
        page.wait_for_timeout(500)

        # ---- Attach CV ----
        result.cv_attached = _attach_cv(page, adapter, cv_path)

        # ---- Cover letter ----
        result.cover_letter_injected = _inject_cover_letter(page, cover_letter_text)

        # ---- Consent checkboxes ----
        _tick_consent_checkboxes(page)
        page.wait_for_timeout(300)

        # ---- Escalation checks ----
        if not adapter.get("auto_submit_safe", False):
            result.screenshot_path = _screenshot(page, job_id, "prefilled")
            result.status = "escalated"
            result.reason = f"platform_manual_only ({platform})"
            return result

        filled_count  = sum(1 for v in fill_res.values() if v == "filled")
        valued_count  = sum(1 for v in fill_res.values() if v != "no_data")
        fill_rate = filled_count / valued_count if valued_count else 0.0
        threshold = adapter.get("escalation_threshold", 0.5)

        if fill_rate < threshold:
            result.screenshot_path = _screenshot(page, job_id, "low_fill")
            result.status = "escalated"
            result.reason = f"fill_rate_too_low ({filled_count}/{valued_count} = {fill_rate:.0%} < {threshold:.0%})"
            return result

        # ---- Find submit button ----
        submit_btn = None
        for sel in adapter.get("submit_selectors", []):
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=1500):
                    submit_btn = loc
                    break
            except Exception:
                continue

        if submit_btn is None:
            result.screenshot_path = _screenshot(page, job_id, "no_submit_btn")
            result.status = "escalated"
            result.reason = "submit_button_not_found"
            return result

        # ---- Final CAPTCHA check (some appear after filling) ----
        if _check_captcha(page):
            result.screenshot_path = _screenshot(page, job_id, "captcha_post_fill")
            result.status = "escalated"
            result.reason = "captcha_detected_post_fill"
            return result

        # ---- SUBMIT ----
        logger.info("Clicking submit for %s @ %s", job.get("title"), job.get("company"))
        submit_btn.click()
        page.wait_for_timeout(3000)   # wait for confirmation page

        # ---- Verify success ----
        if _detect_success(page, adapter):
            result.screenshot_path = _screenshot(page, job_id, "success")
            result.status = "submitted"
            result.reason = ""
        else:
            # Could be an error state or a slow page — take screenshot for review
            result.screenshot_path = _screenshot(page, job_id, "uncertain")
            result.status = "escalated"
            result.reason = "success_not_confirmed — check screenshot"

        return result

    except Exception as exc:
        logger.error("auto_apply error: %s", exc, exc_info=True)
        result.status = "failed"
        result.reason = str(exc)
        return result

    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            playwright.stop()
        except Exception:
            pass
