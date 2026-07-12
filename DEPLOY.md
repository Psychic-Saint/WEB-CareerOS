# WEB CareerOS™ — Deployment Guide
### Run the pipeline 24/7 and access the dashboard from anywhere

---

## Overview

| Component | Where it runs | Free? |
|---|---|---|
| Daily pipeline (discover + apply) | GitHub Actions | ✅ Free |
| Live dashboard | Streamlit Community Cloud | ✅ Free |
| Job database (SQLite) | GitHub repo (auto-committed) | ✅ Free |

---

## STEP 1 — Push the project to GitHub

1. Create a **private** repo at https://github.com/new  
   Name it something like `web-careeros` (keep it private — it holds your .env logic)

2. In CMD, from your project folder:
   ```
   cd "C:\Users\Teddy\Downloads\WEB & Dev Projects\eddie_job_pipeline_v5"
   git init
   git add .
   git commit -m "Initial commit — WEB CareerOS v5"
   git remote add origin https://github.com/YOUR_USERNAME/web-careeros.git
   git push -u origin main
   ```

3. Make sure `.env` is listed in `.gitignore` (it already is — never commit it).

---

## STEP 2 — Add Secrets to GitHub

Go to: **GitHub → your repo → Settings → Secrets and variables → Actions → New repository secret**

Add these secrets one by one:

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Claude API key from .env |
| `GMAIL_APP_PASSWORD` | `zgjy dmlv nzqo zelt` |
| `APPLICANT_PHONE` | `+27 84 323 2662` |
| `APPLICANT_ID_NUMBER` | Your SA ID (leave blank if not needed) |
| `CV_DATA_BASE64` | See below ↓ |

### How to encode your CV as base64

In CMD (Windows):
```
certutil -encode "C:\Users\Teddy\OneDrive - Camblish Training Institute\Documents\Eddie Bila\2026\Eddie_Bila_Comprehensive_Resume_V072026.pdf" cv_encoded.txt
```
Open `cv_encoded.txt`, copy everything **except** the first and last lines (`-----BEGIN CERTIFICATE-----` / `-----END CERTIFICATE-----`), and paste it as the `CV_DATA_BASE64` secret.

Or in PowerShell:
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\Users\Teddy\OneDrive - Camblish Training Institute\Documents\Eddie Bila\2026\Eddie_Bila_Comprehensive_Resume_V072026.pdf")) | clip
```
This copies the base64 string straight to your clipboard — paste it as the secret.

---

## STEP 3 — Test the GitHub Actions pipeline

1. Go to: **GitHub → your repo → Actions → WEB CareerOS — Daily Pipeline**
2. Click **Run workflow** → select `--now` → click **Run workflow**
3. Watch the logs — it should discover jobs, score them, and apply where possible
4. After it completes, the SQLite file will be auto-committed back to the repo

The pipeline now also runs automatically every day at **07:00 SAST**.

---

## STEP 4 — Deploy the Dashboard on Streamlit Community Cloud

1. Go to: https://share.streamlit.io → **Sign in with GitHub**
2. Click **New app**
3. Fill in:
   - **Repository:** `YOUR_USERNAME/web-careeros`
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
4. Click **Deploy**

Your dashboard will be live at a URL like:  
`https://your-username-web-careeros-streamlit-app-xxxxxx.streamlit.app`

Bookmark it — you can open it from your phone while travelling.

### Add secrets to Streamlit Cloud (so it can read your config)

In Streamlit Cloud → your app → **Settings → Secrets**, add:
```toml
ANTHROPIC_API_KEY = "sk-ant-..."
GMAIL_APP_PASSWORD = "zgjy dmlv nzqo zelt"
APPLICANT_FULL_NAME = "Eddie Bila"
APPLICANT_EMAIL = "eddiebila10@gmail.com"
APPLICANT_PHONE = "+27 84 323 2662"
CV_PATH = ""
AUTO_SUBMIT_ENABLED = "true"
AUTO_COVER_LETTER = "true"
DAILY_AUTO_APPLY_LIMIT = "15"
AUTO_APPLY_MIN_SCORE = "60"
MIN_FIT_SCORE = "55"
```

---

## STEP 5 — How to update your CV

When you update your CV, re-encode it and update the `CV_DATA_BASE64` GitHub secret.
The next pipeline run will automatically use the new version.

---

## Running locally (while at home)

```
cd "C:\Users\Teddy\Downloads\WEB & Dev Projects\eddie_job_pipeline_v5"

# Run one pipeline cycle now
python run_daily.py --now

# Open dashboard
streamlit run app/review_app.py
```

---

## Architecture Summary

```
GitHub Actions (daily 07:00 SAST)
    │
    ├─ discovers jobs (8 sources)
    ├─ scores with Claude AI against your CV
    ├─ auto-applies via Playwright + Gmail
    └─ commits job_queue.sqlite3 back to repo
                │
                ▼
    Streamlit Cloud (always on)
        reads job_queue.sqlite3 from repo
        shows live dashboard with all jobs,
        cover letters, and manual action queue
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Dashboard shows 0 jobs | Run the pipeline at least once (`python run_daily.py --now`) |
| GitHub Actions fails on Playwright | Check that `playwright install chromium --with-deps` ran in the logs |
| CV not attaching to emails | Check `CV_DATA_BASE64` secret is correct (re-encode and re-paste) |
| Streamlit shows import errors | Check that all packages in `requirements.txt` are installed on Cloud |
| `openpyxl` not found | Run: `pip install openpyxl` |
