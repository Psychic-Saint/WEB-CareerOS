# Eddie's Job Application Pipeline — v5 (Auto-Apply)

**You provide the CV. The system finds jobs, scores them, applies for you, and only surfaces ones it can't handle.**

---

## How It Works

```
7:00 AM daily
  ↓
DISCOVER  ← pulls new jobs from RemoteOK, Jobicy, Arbeitnow
  ↓
SCORE     ← Claude reads your CV vs each JD → fit score 0-100
  ↓  (< 55? discard silently)
AUTO-APPLY (score ≥ 60)
  ↓
  ┌─ Simple ATS (Greenhouse, Lever, Simplify.hr, Ashby, Workable…)
  │    → fills form, attaches CV, generates cover letter, clicks Submit
  │    → status = submitted ✅
  │
  └─ Complex / bot-protected (Workday, LinkedIn, CAPTCHA detected, low fill rate)
       → takes screenshot of pre-filled form
       → status = escalated ⚠️
       → you handle it in the review app (1 click to open browser)

Evening: open daily_report.html to see what was submitted / what needs you
```

---

## Quick Start

### 1. Install
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure
```bash
cp config/.env.example .env
# Fill in: ANTHROPIC_API_KEY, CV_PATH, APPLICANT_PHONE, APPLICANT_LINKEDIN
# Everything else has sensible defaults
```

### 3. Start the pipeline
```bash
python run_daily.py
```
Runs once immediately, then fires every day at 07:00 SAST. Leave it running.

### 4. Check what happened
Open `daily_report.html` in your browser — or run the review app:
```bash
streamlit run app/review_app.py
```

---

## Other Commands

```bash
# Add any job URL directly (skips scoring — goes straight to apply queue)
python add_job.py https://pepkorlifestyle.simplify.hr/Vacancy/Apply/cfa52i

# Run just discovery + scoring (no applying)
python run_daily.py --discover

# Run just the apply step (for jobs already in queue)
python run_daily.py --apply

# Open escalated jobs manually (terminal mode, no Streamlit needed)
python open_jobs.py
```

---

## What Gets Auto-Submitted vs Escalated

| Platform | Auto-submit | Why |
|---|---|---|
| Simplify.hr | ✅ Yes | Clean single-page form |
| Greenhouse | ✅ Yes | Reliable structure |
| Lever | ✅ Yes | Simple, consistent |
| Ashby | ✅ Yes | Clean form |
| Workable | ✅ Yes | Reliable |
| Breezy HR | ✅ Yes | Simple |
| Recruitee | ✅ Yes | Simple |
| Generic (unknown) | ✅ Tries | Strict 65% fill threshold |
| SmartRecruiters | ⚠️ Escalate | Bot detection |
| Workday | ⚠️ Escalate | Multi-step, needs account |
| LinkedIn Easy Apply | ⚠️ Escalate | Multi-step panels |
| Indeed | ⚠️ Escalate | Multi-step |
| Any with CAPTCHA | ⚠️ Escalate | Always escalate |

**Escalated = the system pre-filled the form and left the browser ready. You just review and click Submit.**

---

## Folder Structure

```
job_pipeline/
├── run_daily.py          ← START HERE — daily orchestrator + scheduler
├── add_job.py            ← add any URL manually
├── open_jobs.py          ← terminal mode: open escalated jobs
├── daily_report.html     ← generated each run (open in browser)
├── .env                  ← YOUR secrets (never commit)
│
├── config/
│   ├── settings.py       ← all settings (reads from .env)
│   └── .env.example      ← template
│
├── fill_engine/
│   ├── platform_adapters.py  ← per-ATS field selectors + submit buttons
│   ├── auto_apply.py         ← fill + CAPTCHA check + submit + success verify
│   └── playwright_filler.py  ← manual-assist mode (opens visible browser)
│
├── ai/
│   └── scorer.py         ← CV vs JD fit scoring + cover letter generation
│
├── discovery/
│   └── sources.py        ← RemoteOK, Jobicy, Arbeitnow fetchers
│
├── job_queue/
│   └── store.py          ← SQLite queue
│
├── app/
│   ├── review_app.py     ← Streamlit dashboard (escalated + submitted)
│   └── report.py         ← HTML report writer
│
├── browser_profile/      ← persistent login session (auto-created)
└── screenshots/          ← snapshots taken at escalation/success (auto-created)
```

---

## Important: First Run Logins

The browser uses a persistent profile (like a regular Chrome user profile). The **first time** a site needs login (LinkedIn, Indeed), the system will pause and ask you to log in manually in the visible window. After that, the session is remembered forever — no re-login needed.

Sites like Simplify.hr, Greenhouse, and Lever don't need login at all.

---

## Safety Guarantees

- **Passwords**: never stored, never typed by the script
- **Auto-submit**: only on platforms explicitly marked `auto_submit_safe = True`
- **CAPTCHA**: always escalates — never attempts to bypass
- **Daily limit**: `DAILY_AUTO_APPLY_LIMIT` (default 15) caps applications per day
- **Score gate**: only applies to jobs scoring ≥ `AUTO_APPLY_MIN_SCORE` (default 60)
- **Screenshot**: taken for every escalated job so you can see exactly what the form looked like
