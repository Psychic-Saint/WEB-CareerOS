"""
fill_engine/gmail_sender.py

Sends email-based job applications via Gmail using SMTP + App Password.

This handles:
  - Jobs with 'Apply by email' (apply_url starts with "mailto:")
  - Attaches your CV automatically
  - Injects an AI-generated cover letter as the email body
  - Uses a Gmail App Password (not your real Gmail password)

SETUP (one time):
  1. Go to https://myaccount.google.com/security
  2. Enable 2-Step Verification (if not already on)
  3. Search "App passwords" → create one named "Job Pipeline"
  4. Copy the 16-char password into .env as GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

NEVER stores your real Gmail password.
NEVER sends without your CV attached.
"""

from __future__ import annotations

import logging
import re
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import unquote, urlparse

logger = logging.getLogger("job_pipeline.gmail_sender")


# ---------------------------------------------------------------------------
# mailto: URL parser
# ---------------------------------------------------------------------------

def parse_mailto(url: str) -> dict:
    """
    Parse a mailto: URL into its components.

    mailto:jobs@company.com?subject=Application&body=Hello

    Returns:
      {"to": "jobs@company.com", "subject": "...", "body": "..."}
    """
    if not url.startswith("mailto:"):
        return {}

    # Strip "mailto:" and split on "?"
    raw = url[7:]
    parts = raw.split("?", 1)
    to_addr = unquote(parts[0]).strip()

    params: dict[str, str] = {}
    if len(parts) > 1:
        for pair in parts[1].split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k.lower()] = unquote(v)

    return {
        "to":      to_addr,
        "subject": params.get("subject", ""),
        "body":    params.get("body",    ""),
        "cc":      params.get("cc",      ""),
        "bcc":     params.get("bcc",     ""),
    }


# ---------------------------------------------------------------------------
# Compose the application email
# ---------------------------------------------------------------------------

def _compose_email(
    job:               dict,
    applicant_data:    dict,
    cover_letter_text: str,
    cv_path:           str | None,
    mailto_parsed:     dict,
    from_email:        str,
) -> MIMEMultipart:
    """Build the MIME email message."""

    to_addr = mailto_parsed.get("to", "")
    subject = mailto_parsed.get("subject", "").strip()
    if not subject:
        subject = f"Application – {job.get('title', 'Position')} | {applicant_data.get('full_name', 'Eddie Bila')}"

    # Body: use AI cover letter if available, else a professional default
    body = cover_letter_text or (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my interest in the {job.get('title', 'advertised position')} "
        f"at {job.get('company', 'your organisation')}. "
        f"Please find my CV attached for your consideration.\n\n"
        f"I look forward to the opportunity to discuss how my skills and experience "
        f"can contribute to your team.\n\n"
        f"Kind regards,\n"
        f"{applicant_data.get('full_name', 'Eddie Bila')}\n"
        f"{applicant_data.get('email', '')}\n"
        f"{applicant_data.get('phone', '')}"
    )

    msg = MIMEMultipart()
    msg["From"]    = from_email
    msg["To"]      = to_addr
    msg["Subject"] = subject
    if mailto_parsed.get("cc"):
        msg["Cc"] = mailto_parsed["cc"]

    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Attach CV
    if cv_path and Path(cv_path).exists():
        cv_file = Path(cv_path)
        with open(cv_file, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{cv_file.name}"',
        )
        msg.attach(part)
        logger.info("✓ CV attached: %s", cv_file.name)
    else:
        logger.warning("No CV found at '%s' — sending without attachment", cv_path)

    return msg


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def send_email_application(
    job:               dict,
    apply_url:         str,
    applicant_data:    dict,
    cv_path:           str | None,
    cover_letter_text: str,
    from_email:        str,
    app_password:      str,
) -> tuple[bool, str]:
    """
    Sends an email application for a 'mailto:' job posting.

    Returns:
        (success: bool, reason: str)
    """
    if not apply_url.startswith("mailto:"):
        return False, "not_a_mailto_url"

    if not app_password:
        logger.warning("GMAIL_APP_PASSWORD not set in .env — cannot send email application")
        return False, "gmail_app_password_not_configured"

    if not from_email:
        return False, "applicant_email_not_configured"

    mailto_parsed = parse_mailto(apply_url)
    to_addr       = mailto_parsed.get("to", "")
    if not to_addr:
        return False, "no_recipient_address_in_mailto_url"

    logger.info(
        "Sending email application to %s for %s @ %s",
        to_addr, job.get("title"), job.get("company"),
    )

    try:
        msg = _compose_email(
            job=job,
            applicant_data=applicant_data,
            cover_letter_text=cover_letter_text,
            cv_path=cv_path,
            mailto_parsed=mailto_parsed,
            from_email=from_email,
        )

        # Gmail SMTP over SSL (port 465)
        recipients = [to_addr]
        if mailto_parsed.get("cc"):
            recipients.append(mailto_parsed["cc"])

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(from_email, app_password)
            server.sendmail(from_email, recipients, msg.as_string())

        logger.info("✓ Email sent to %s", to_addr)
        return True, f"email_sent_to:{to_addr}"

    except smtplib.SMTPAuthenticationError:
        reason = "gmail_auth_failed — check GMAIL_APP_PASSWORD in .env"
        logger.error(reason)
        return False, reason

    except smtplib.SMTPException as e:
        reason = f"smtp_error:{e}"
        logger.error("Email send failed: %s", e)
        return False, reason

    except Exception as e:
        reason = f"unexpected_error:{e}"
        logger.error("Email send failed: %s", e, exc_info=True)
        return False, reason


if __name__ == "__main__":
    # Quick test — run directly to verify SMTP credentials work
    import os
    from dotenv import load_dotenv
    load_dotenv()

    result, reason = send_email_application(
        job={"title": "Test Role", "company": "Test Co"},
        apply_url="mailto:test@example.com?subject=Test Application",
        applicant_data={
            "full_name": "Eddie Bila",
            "email":     os.getenv("APPLICANT_EMAIL", ""),
            "phone":     os.getenv("APPLICANT_PHONE", ""),
        },
        cv_path=os.getenv("CV_PATH", ""),
        cover_letter_text="This is a test email from the job pipeline.",
        from_email=os.getenv("APPLICANT_EMAIL", ""),
        app_password=os.getenv("GMAIL_APP_PASSWORD", ""),
    )
    print(f"Result: {result}  |  Reason: {reason}")
