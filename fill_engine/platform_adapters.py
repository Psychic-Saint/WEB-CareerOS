"""
fill_engine/platform_adapters.py  — v5: per-platform selectors + auto-submit config

Each adapter now includes:
  auto_submit_safe      bool  — True = system can click Submit automatically
                                False = must escalate to Eddie for manual submit
  submit_selectors      list  — CSS selectors to find the Submit/Apply button
  success_patterns      list  — lowercase text snippets found on a success/confirmation page
  escalation_threshold  float — min fill-rate (0-1) before escalating even on safe platforms
"""

from __future__ import annotations
from typing import Any


def detect_platform(url: str) -> str:
    u = url.lower()
    if "simplify.hr" in u:                                       return "simplify_hr"
    if "boards.greenhouse.io" in u or "greenhouse.io" in u:      return "greenhouse"
    if "jobs.lever.co" in u or "lever.co" in u:                  return "lever"
    if "myworkdayjobs.com" in u or "workday.com" in u:           return "workday"
    if "linkedin.com/jobs" in u or "linkedin.com/easy-apply" in u: return "linkedin"
    if "smartrecruiters.com" in u:                               return "smartrecruiters"
    if "ashbyhq.com" in u:                                       return "ashby"
    if "teamtailor.com" in u:                                    return "teamtailor"
    if "apply.workable.com" in u or "workable.com" in u:         return "workable"
    if "breezy.hr" in u:                                         return "breezy"
    if "recruitee.com" in u:                                     return "recruitee"
    if "secure.indeed.com" in u or "indeed.com" in u:           return "indeed"
    return "generic"


PLATFORM_ADAPTERS: dict[str, dict[str, Any]] = {

    # ------------------------------------------------------------------ #
    # Simplify.hr  ✅ auto-submit safe                                    #
    # ------------------------------------------------------------------ #
    "simplify_hr": {
        "tested_date": "2026-07",
        "requires_login": False,
        "auto_submit_safe": True,
        "escalation_threshold": 0.5,   # escalate if <50% of fields filled
        "field_map": {
            "first_name":   ['input[name="firstName"]', 'input[id="firstName"]',
                             'input[placeholder*="First name" i]'],
            "last_name":    ['input[name="lastName"]',  'input[id="lastName"]',
                             'input[placeholder*="Last name" i]'],
            "email":        ['input[type="email"]', 'input[name="email"]'],
            "phone":        ['input[type="tel"]', 'input[name="phone"]',
                             'input[name="mobile"]', 'input[placeholder*="phone" i]'],
            "linkedin_url": ['input[name="linkedin"]', 'input[name="linkedinUrl"]',
                             'input[placeholder*="LinkedIn" i]'],
            "id_number":    ['input[name="idNumber"]', 'input[name="id_number"]',
                             'input[placeholder*="ID number" i]',
                             'input[placeholder*="identity number" i]'],
        },
        "cv_upload_selector": 'input[type="file"]',
        "submit_selectors": [
            'button[type="submit"]',
            'button:has-text("Apply")',
            'button:has-text("Submit")',
            'input[type="submit"]',
        ],
        "success_patterns": [
            "thank you", "application submitted", "application received",
            "we'll be in touch", "your application has been",
            "successfully applied", "we have received your",
        ],
        "post_fill_notes": (
            "SA-specific fields (EE/race, disability) require manual input — "
            "check before auto-submit runs. ID number is filled from .env."
        ),
    },

    # ------------------------------------------------------------------ #
    # Greenhouse  ✅ auto-submit safe                                     #
    # ------------------------------------------------------------------ #
    "greenhouse": {
        "tested_date": "2026-07",
        "requires_login": False,
        "auto_submit_safe": True,
        "escalation_threshold": 0.5,
        "field_map": {
            "first_name": ['input#first_name', 'input[name="job_application[first_name]"]'],
            "last_name":  ['input#last_name',  'input[name="job_application[last_name]"]'],
            "email":      ['input#email',       'input[name="job_application[email]"]', 'input[type="email"]'],
            "phone":      ['input#phone',       'input[name="job_application[phone]"]', 'input[type="tel"]'],
            "linkedin_url": ['input[placeholder*="LinkedIn" i]'],
        },
        "cv_upload_selector": 'input#resume',
        "submit_selectors": [
            'input#submit_app',
            'button[type="submit"]',
            'input[type="submit"][value*="Submit" i]',
            'button:has-text("Submit Application")',
        ],
        "success_patterns": [
            "thank you for applying", "application submitted",
            "we'll review your application", "your application has been received",
        ],
        "post_fill_notes": "Check for work-auth dropdowns and custom questions before submit.",
    },

    # ------------------------------------------------------------------ #
    # Lever  ✅ auto-submit safe                                          #
    # ------------------------------------------------------------------ #
    "lever": {
        "tested_date": "2026-07",
        "requires_login": False,
        "auto_submit_safe": True,
        "escalation_threshold": 0.5,
        "field_map": {
            "full_name":    ['input[name="name"]', 'input[placeholder*="Full name" i]'],
            "email":        ['input[name="email"]', 'input[type="email"]'],
            "phone":        ['input[name="phone"]', 'input[type="tel"]'],
            "linkedin_url": ['input[name="urls[LinkedIn]"]', 'input[placeholder*="LinkedIn" i]'],
            "org":          ['input[name="org"]', 'input[placeholder*="Current company" i]'],
        },
        "cv_upload_selector": 'input[name="resume"]',
        "submit_selectors": [
            'button[type="submit"]',
            'button:has-text("Submit Application")',
            'button:has-text("Apply")',
        ],
        "success_patterns": [
            "application submitted", "thank you", "we've received",
            "you've applied", "your application is in",
        ],
        "post_fill_notes": "Lever forms are clean — usually submits without issues.",
    },

    # ------------------------------------------------------------------ #
    # Ashby  ✅ auto-submit safe                                          #
    # ------------------------------------------------------------------ #
    "ashby": {
        "tested_date": "2026-07",
        "requires_login": False,
        "auto_submit_safe": True,
        "escalation_threshold": 0.5,
        "field_map": {
            "full_name":    ['input[name="name"]', 'input[placeholder*="name" i]'],
            "email":        ['input[name="email"]', 'input[type="email"]'],
            "phone":        ['input[name="phone"]', 'input[type="tel"]'],
            "linkedin_url": ['input[name="linkedin"]', 'input[placeholder*="linkedin" i]'],
        },
        "cv_upload_selector": 'input[type="file"]',
        "submit_selectors": [
            'button[type="submit"]',
            'button:has-text("Submit")',
            'button:has-text("Apply")',
        ],
        "success_patterns": ["thank you", "application received", "we'll be in touch"],
        "post_fill_notes": "Ashby forms are simple and reliable.",
    },

    # ------------------------------------------------------------------ #
    # Workable  ✅ auto-submit safe                                       #
    # ------------------------------------------------------------------ #
    "workable": {
        "tested_date": "2026-07",
        "requires_login": False,
        "auto_submit_safe": True,
        "escalation_threshold": 0.5,
        "field_map": {
            "first_name":   ['input[name="firstname"]', 'input[id*="first" i]'],
            "last_name":    ['input[name="lastname"]',  'input[id*="last" i]'],
            "email":        ['input[name="email"]', 'input[type="email"]'],
            "phone":        ['input[name="phone"]', 'input[type="tel"]'],
            "linkedin_url": ['input[name="linkedin"]', 'input[placeholder*="LinkedIn" i]'],
        },
        "cv_upload_selector": 'input[type="file"]',
        "submit_selectors": ['button[type="submit"]', 'button:has-text("Apply")'],
        "success_patterns": ["thank you", "application received", "successfully applied"],
        "post_fill_notes": "May have a cover letter textarea — check before submitting.",
    },

    # ------------------------------------------------------------------ #
    # Breezy HR  ✅ auto-submit safe                                      #
    # ------------------------------------------------------------------ #
    "breezy": {
        "tested_date": "2026-07",
        "requires_login": False,
        "auto_submit_safe": True,
        "escalation_threshold": 0.5,
        "field_map": {
            "full_name": ['input[name="name"]'],
            "email":     ['input[name="email"]', 'input[type="email"]'],
            "phone":     ['input[name="phone"]', 'input[type="tel"]'],
        },
        "cv_upload_selector": 'input[type="file"]',
        "submit_selectors": ['button[type="submit"]', 'button:has-text("Submit")'],
        "success_patterns": ["thank you", "application submitted"],
        "post_fill_notes": "Usually simple. LinkedIn/portfolio URL field common.",
    },

    # ------------------------------------------------------------------ #
    # Recruitee  ✅ auto-submit safe                                      #
    # ------------------------------------------------------------------ #
    "recruitee": {
        "tested_date": "2026-07",
        "requires_login": False,
        "auto_submit_safe": True,
        "escalation_threshold": 0.5,
        "field_map": {
            "full_name": ['input[name="name"]'],
            "email":     ['input[name="email"]', 'input[type="email"]'],
            "phone":     ['input[name="phone"]', 'input[type="tel"]'],
        },
        "cv_upload_selector": 'input[type="file"]',
        "submit_selectors": ['button[type="submit"]', 'button:has-text("Apply")'],
        "success_patterns": ["thank you", "application received"],
        "post_fill_notes": "Check for GDPR consent checkbox — auto-submit will only proceed if it can be ticked.",
    },

    # ------------------------------------------------------------------ #
    # SmartRecruiters  ⚠️  escalate — they have bot detection           #
    # ------------------------------------------------------------------ #
    "smartrecruiters": {
        "tested_date": "2026-07",
        "requires_login": False,
        "auto_submit_safe": False,
        "escalation_threshold": 0.4,
        "field_map": {
            "first_name": ['input[name="firstName"]', 'input[placeholder*="First" i]'],
            "last_name":  ['input[name="lastName"]',  'input[placeholder*="Last" i]'],
            "email":      ['input[name="email"]', 'input[type="email"]'],
            "phone":      ['input[name="phoneNumber"]', 'input[type="tel"]'],
        },
        "cv_upload_selector": 'input[type="file"]',
        "submit_selectors": ['button[type="submit"]'],
        "success_patterns": ["thank you", "application submitted"],
        "post_fill_notes": "SmartRecruiters has bot detection — escalated to you for manual submit.",
    },

    # ------------------------------------------------------------------ #
    # Workday  ❌ escalate — complex multi-step, requires account        #
    # ------------------------------------------------------------------ #
    "workday": {
        "tested_date": "2026-07",
        "requires_login": True,
        "auto_submit_safe": False,
        "escalation_threshold": 0.3,
        "field_map": {
            "email": ['input[data-automation-id="email"]'],
            "phone": ['input[data-automation-id="phone"]'],
        },
        "cv_upload_selector": 'input[data-automation-id="file-upload-input-ref"]',
        "submit_selectors": ['button[data-automation-id="bottom-navigation-next-button"]'],
        "success_patterns": ["thank you", "submitted", "application complete"],
        "post_fill_notes": "⚠️  Workday requires a per-company account and has many steps — escalated to you.",
    },

    # ------------------------------------------------------------------ #
    # LinkedIn Easy Apply  ❌ escalate — multi-step panels               #
    # ------------------------------------------------------------------ #
    "linkedin": {
        "tested_date": "2026-07",
        "requires_login": True,
        "login_url": "https://www.linkedin.com/login",
        "logged_in_selector": '[data-test-app-aware-link]',
        "auto_submit_safe": False,
        "escalation_threshold": 0.0,
        "field_map": {
            "phone": ['input[id*="phoneNumber"]'],
        },
        "cv_upload_selector": None,
        "submit_selectors": ['button[aria-label*="Submit application" i]'],
        "success_patterns": ["application submitted", "you applied"],
        "post_fill_notes": "LinkedIn Easy Apply is multi-step — escalated to you to work through the panels.",
    },

    # ------------------------------------------------------------------ #
    # Indeed  ❌ escalate — multi-step, uses stored resume               #
    # ------------------------------------------------------------------ #
    "indeed": {
        "tested_date": "2026-07",
        "requires_login": True,
        "login_url": "https://secure.indeed.com/account/login",
        "logged_in_selector": '[data-gnav-element-name="AccountMenu"]',
        "auto_submit_safe": False,
        "escalation_threshold": 0.0,
        "field_map": {
            "phone": ['input[id*="phone" i]', 'input[type="tel"]'],
        },
        "cv_upload_selector": None,
        "submit_selectors": ['button:has-text("Submit your application")'],
        "success_patterns": ["application submitted", "you applied"],
        "post_fill_notes": "Indeed is multi-step — escalated to you.",
    },

    # ------------------------------------------------------------------ #
    # Generic fallback  ✅ attempts auto-submit but with strict threshold #
    # ------------------------------------------------------------------ #
    "generic": {
        "tested_date": None,
        "requires_login": False,
        "auto_submit_safe": True,
        "escalation_threshold": 0.65,   # stricter — less confident about selectors
        "field_map": {
            "first_name":   ['input[name*="first" i]', 'input[id*="first" i]',
                             'input[placeholder*="First name" i]'],
            "last_name":    ['input[name*="last" i]',  'input[id*="last" i]',
                             'input[placeholder*="Last name" i]'],
            "full_name":    ['input[name="name"]', 'input[autocomplete="name"]',
                             'input[placeholder*="Full name" i]'],
            "email":        ['input[type="email"]', 'input[name*="email" i]',
                             'input[placeholder*="email" i]'],
            "phone":        ['input[type="tel"]', 'input[name*="phone" i]',
                             'input[placeholder*="phone" i]', 'input[placeholder*="mobile" i]'],
            "linkedin_url": ['input[name*="linkedin" i]', 'input[placeholder*="LinkedIn" i]'],
        },
        "cv_upload_selector": 'input[type="file"]',
        "submit_selectors": [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit")',
            'button:has-text("Apply Now")',
            'button:has-text("Apply")',
            'button:has-text("Send Application")',
        ],
        "success_patterns": [
            "thank you", "application submitted", "application received",
            "we'll be in touch", "successfully applied", "application complete",
            "your application has been", "we have received",
        ],
        "post_fill_notes": "Generic adapter used — review fill report if anything looks off.",
    },
}
