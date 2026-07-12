"""
app/review_app.py — WEB CareerOS™ Live Dashboard

Run locally:   streamlit run app/review_app.py
Hosted:        Streamlit Community Cloud → https://share.streamlit.io
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_queue.store import JobQueueStore
import config.settings as settings

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="WEB CareerOS",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# WEB Brand CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  :root {
    --web-dark:   #010d0f;
    --web-card:   #021a1e;
    --web-cyan:   #00e5ff;
    --web-cyan2:  #00bcd4;
    --web-muted:  #7ecdd8;
    --web-white:  #e0f7fa;
    --web-accent: #00bfa5;
  }
  html, body, .stApp { background: var(--web-dark) !important; }
  .stApp { color: var(--web-white); }
  h1, h2, h3, h4, h5, h6 { color: var(--web-cyan) !important; }

  [data-testid="stSidebar"] {
    background: #010f12 !important;
    border-right: 1px solid #00e5ff22;
  }
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] p { color: var(--web-muted) !important; }

  .stTabs [data-baseweb="tab-list"] {
    background: var(--web-card);
    border-radius: 10px;
    padding: 4px;
    gap: 4px;
  }
  .stTabs [data-baseweb="tab"] { color: var(--web-muted) !important; border-radius: 7px; }
  .stTabs [aria-selected="true"] {
    background: var(--web-cyan) !important;
    color: var(--web-dark) !important;
    font-weight: 700;
  }

  [data-testid="stMetricValue"] { color: var(--web-cyan) !important; font-weight: 800; }
  [data-testid="stMetricLabel"] { color: var(--web-muted) !important; }

  .stButton > button {
    background: var(--web-card) !important;
    border: 1px solid var(--web-cyan) !important;
    color: var(--web-cyan) !important;
    border-radius: 8px;
    font-weight: 600;
    transition: all .2s;
  }
  .stButton > button:hover {
    background: var(--web-cyan) !important;
    color: var(--web-dark) !important;
  }
  .stDownloadButton > button {
    background: var(--web-accent) !important;
    border: none !important;
    color: white !important;
    font-weight: 700;
    border-radius: 8px;
  }
  .badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .04em;
  }
  .job-card {
    background: var(--web-card);
    border: 1px solid #00e5ff22;
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 12px;
  }
  .job-card h4 { color: var(--web-white); margin: 0 0 4px; }
  .job-card .meta { color: var(--web-muted); font-size: .85rem; }
  .stat-bar {
    background: var(--web-card);
    border: 1px solid #00e5ff22;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 8px;
  }
  .stat-bar .num { font-size: 1.8rem; font-weight: 800; color: var(--web-cyan); }
  .stat-bar .lbl {
    font-size: .75rem;
    color: var(--web-muted);
    text-transform: uppercase;
    letter-spacing: .08em;
  }
  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: var(--web-dark); }
  ::-webkit-scrollbar-thumb { background: #00e5ff44; border-radius: 4px; }
  hr { border-color: #00e5ff22 !important; }
  .stTextInput input, .stSelectbox select {
    background: var(--web-card) !important;
    color: var(--web-white) !important;
    border: 1px solid #00e5ff33 !important;
  }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SOURCE_COLORS = {
    "remoteok":       "#ff4d00",
    "jobicy":         "#6366f1",
    "arbeitnow":      "#059669",
    "weworkremotely": "#0891b2",
    "workingnomads":  "#7c3aed",
    "himalayas":      "#0284c7",
    "jobspresso":     "#b45309",
    "remoteco":       "#be185d",
    "linkedin":       "#0077b5",
    "indeed":         "#003a9b",
    "facebook":       "#1877f2",
    "twitter":        "#1da1f2",
    "email":          "#00bfa5",
}

STATUS_CFG = {
    "submitted":      ("✅ Auto-Applied",    "#00c853"),
    "escalated":      ("⚠️ Needs You",        "#ffb300"),
    "rejected":       ("❌ Poor Fit",          "#ff5252"),
    "approved":       ("🟢 Queued",            "#00bfa5"),
    "new":            ("🔵 New",               "#607d8b"),
    "scored":         ("🟡 Scored",            "#ffd740"),
    "failed":         ("💥 Failed",             "#e040fb"),
    "skipped":        ("⏭️ Skipped",           "#546e7a"),
    "pending_review": ("👁 In Review",         "#7ecdd8"),
    "drafted":        ("📝 Drafted",           "#7ecdd8"),
}


def source_badge(source: str) -> str:
    c = SOURCE_COLORS.get(source, "#7ecdd8")
    return f'<span class="badge" style="background:{c}22;color:{c};border:1px solid {c}44">{source.upper()}</span>'


def status_badge(status: str) -> str:
    label, c = STATUS_CFG.get(status, (status.upper(), "#7ecdd8"))
    return f'<span class="badge" style="background:{c}22;color:{c};border:1px solid {c}44">{label}</span>'


def action_label(job: dict) -> str:
    s = job.get("status", "")
    n = (job.get("notes") or "").lower()
    if s == "submitted":
        return "✉️ Email Sent" if ("email_sent_to" in n or "platform=email" in n) else "✅ Form Submitted"
    if s == "escalated":
        if "captcha" in n:      return "🚧 CAPTCHA Block"
        if "manual_only" in n:  return "🔒 Manual Platform"
        if "fill_rate" in n:    return "📝 Form Incomplete"
        return "⚠️ Escalated"
    if s == "rejected": return "❌ Poor Fit"
    if s == "approved": return "🟢 Queued"
    return s.replace("_", " ").title()


def fmt_date(iso: str) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b %Y")
    except Exception:
        return iso[:10] if len(iso) >= 10 else iso


def load_cover_letter(job: dict) -> str:
    if job.get("cover_letter_text"):
        return job["cover_letter_text"]
    p = job.get("cover_letter_path")
    if p and Path(p).exists():
        try:
            return Path(p).read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


# ---------------------------------------------------------------------------
# Data loader
# ---------------------------------------------------------------------------
@st.cache_resource
def get_store():
    return JobQueueStore(settings.QUEUE_DB_PATH)


def load_data():
    store  = get_store()
    jobs   = store.get_all_jobs(limit=2000)
    counts = store.counts_by_status()
    return store, jobs, counts


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    # ── Logo ──────────────────────────────────────────────────
    _logo_path = Path(__file__).parent / "assets" / "web_logo.png"
    if _logo_path.exists():
        st.image(str(_logo_path), use_column_width=True)
        st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:#021a1e;border:1px solid #00e5ff33;border-radius:12px;
          padding:18px 16px;text-align:center;margin-bottom:12px">
          <div style="font-size:30px;font-weight:900;color:#00e5ff;letter-spacing:6px;
            font-family:'Segoe UI',sans-serif">WEB</div>
          <div style="font-size:10px;color:#7ecdd8;letter-spacing:4px;
            text-transform:uppercase;margin-top:3px">CareerOS™</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px">
      <span style="width:8px;height:8px;background:#00c853;border-radius:50%;
        display:inline-block;box-shadow:0 0 6px #00c853"></span>
      <span style="color:#7ecdd8;font-size:.82rem;font-weight:600">LIVE PIPELINE</span>
    </div>
    """, unsafe_allow_html=True)

    store, all_jobs, counts = load_data()

    n_submitted = counts.get("submitted", 0)
    n_escalated = counts.get("escalated", 0)
    n_approved  = counts.get("approved",  0)
    n_rejected  = counts.get("rejected",  0)
    total       = sum(counts.values())

    st.markdown(f"""
    <div class="stat-bar">
      <div class="num">{total}</div>
      <div class="lbl">Total Discovered</div>
    </div>
    <div class="stat-bar">
      <div class="num" style="color:#00c853">{n_submitted}</div>
      <div class="lbl">Auto-Applied For You</div>
    </div>
    <div class="stat-bar">
      <div class="num" style="color:#ffb300">{n_escalated}</div>
      <div class="lbl">Need Your Action</div>
    </div>
    <div class="stat-bar">
      <div class="num" style="color:#ff5252">{n_rejected}</div>
      <div class="lbl">Poor Fit (can override)</div>
    </div>
    <div class="stat-bar">
      <div class="num" style="color:#00bfa5">{n_approved}</div>
      <div class="lbl">Queued to Apply</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    if st.button("🔄  Refresh Data", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

    try:
        from app.excel_export import build_excel_bytes
        xlsx_data = build_excel_bytes(all_jobs)
        st.download_button(
            label="⬇️  Export to Excel",
            data=xlsx_data,
            file_name=f"WEB_CareerOS_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except Exception as exc:
        st.caption(f"Excel unavailable: {exc}")

    st.markdown(
        f"<div style='color:#3d7a85;font-size:.75rem;text-align:center;margin-top:8px'>"
        f"Refreshed {datetime.now().strftime('%H:%M')}</div>",
        unsafe_allow_html=True,
    )


# ============================================================
# MAIN HEADER
# ============================================================
st.markdown("""
<div style="margin-bottom:24px">
  <h1 style="margin:0;font-size:2rem;font-weight:900;color:#00e5ff">🚀 WEB CareerOS™</h1>
  <div style="color:#7ecdd8;font-size:.9rem;margin-top:4px">
    Autonomous Job Application Pipeline — applying on your behalf, 24/7
  </div>
</div>
""", unsafe_allow_html=True)

if n_escalated:
    st.warning(
        f"⚠️ **{n_escalated} job(s) need your attention** — see the **Needs Your Action** tab.",
        icon="🔔",
    )

# ============================================================
# TABS
# ============================================================
tab_ov, tab_all, tab_act, tab_poor, tab_cl = st.tabs([
    "📊 Overview",
    "📋 All Jobs",
    "⚠️ Needs Your Action",
    "🔓 Approve Poor Fit",
    "✉️ Cover Letters",
])

# ─────────────────────────────────────────────────
# TAB 1 — OVERVIEW
# ─────────────────────────────────────────────────
with tab_ov:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Jobs Found",   total)
    c2.metric("Auto-Applied", n_submitted, help="System submitted these on your behalf")
    c3.metric("Need You",     n_escalated, help="CAPTCHA / login required / form incomplete")
    c4.metric("Poor Fit",     n_rejected,  help="Scored below threshold — you can override")
    c5.metric("In Queue",     n_approved,  help="Scored well — applying next run")

    st.markdown("---")

    src_counts = store.counts_by_source()
    if src_counts:
        st.markdown("### 🌐 Jobs by Source")
        cols = st.columns(min(len(src_counts), 4))
        for i, (src, cnt) in enumerate(sorted(src_counts.items(), key=lambda x: -x[1])):
            color = SOURCE_COLORS.get(src, "#7ecdd8")
            with cols[i % 4]:
                st.markdown(f"""
                <div style="background:#021a1e;border:1px solid {color}44;
                  border-left:4px solid {color};border-radius:10px;
                  padding:14px 16px;margin-bottom:8px">
                  <div style="font-size:1.6rem;font-weight:800;color:{color}">{cnt}</div>
                  <div style="font-size:.75rem;color:#7ecdd8;text-transform:uppercase;
                    letter-spacing:.06em">{src}</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🕐 Recent Activity")
    recent = sorted(all_jobs, key=lambda j: j.get("updated_at", ""), reverse=True)[:10]
    for job in recent:
        ca, cb, cc = st.columns([3, 2, 2])
        with ca:
            st.markdown(f"**{job['title']}** — {job['company']}")
        with cb:
            st.markdown(
                source_badge(job.get("source","")) + "&nbsp;" + status_badge(job.get("status","")),
                unsafe_allow_html=True,
            )
        with cc:
            st.markdown(
                f"<span style='color:#7ecdd8;font-size:.82rem'>"
                f"{fmt_date(job.get('updated_at',''))}</span>",
                unsafe_allow_html=True,
            )

# ─────────────────────────────────────────────────
# TAB 2 — ALL JOBS
# ─────────────────────────────────────────────────
with tab_all:
    st.markdown("### 📋 All Discovered Jobs")

    f1, f2, f3, f4 = st.columns([3, 2, 2, 2])
    with f1:
        q = st.text_input("🔍 Search title / company", placeholder="e.g. Project Manager")
    with f2:
        status_f = st.selectbox("Status", ["All"] + sorted({j["status"] for j in all_jobs}))
    with f3:
        source_f = st.selectbox("Source", ["All"] + sorted({j["source"] for j in all_jobs}))
    with f4:
        remote_f = st.selectbox("Location", ["All", "Remote Only", "On-site Only"])

    filtered = all_jobs
    if q:
        ql = q.lower()
        filtered = [j for j in filtered
                    if ql in j.get("title","").lower() or ql in j.get("company","").lower()]
    if status_f != "All":
        filtered = [j for j in filtered if j.get("status") == status_f]
    if source_f != "All":
        filtered = [j for j in filtered if j.get("source") == source_f]
    if remote_f == "Remote Only":
        filtered = [j for j in filtered if j.get("is_remote")]
    elif remote_f == "On-site Only":
        filtered = [j for j in filtered if not j.get("is_remote")]

    st.markdown(
        f"<div style='color:#7ecdd8;font-size:.82rem;margin-bottom:12px'>"
        f"{len(filtered)} jobs shown</div>",
        unsafe_allow_html=True,
    )

    for job in filtered[:200]:
        with st.expander(
            f"{job['title']}  ·  {job['company']}  ·  {job.get('location','')}", expanded=False
        ):
            r1, r2, r3, r4, r5 = st.columns([2, 2, 2, 2, 2])
            with r1:
                st.markdown(source_badge(job.get("source","")), unsafe_allow_html=True)
                loc_txt = "🌐 Remote" if job.get("is_remote") else f"📍 {job.get('location') or 'N/A'}"
                st.markdown(
                    f"<div style='color:#7ecdd8;font-size:.78rem;margin-top:4px'>{loc_txt}</div>",
                    unsafe_allow_html=True,
                )
            with r2:
                st.markdown(status_badge(job.get("status","")), unsafe_allow_html=True)
                st.markdown(
                    f"<div style='color:#7ecdd8;font-size:.78rem;margin-top:4px'>"
                    f"{action_label(job)}</div>",
                    unsafe_allow_html=True,
                )
            with r3:
                score = job.get("fit_score")
                sc = "#00c853" if (score and score >= 70) else ("#ffb300" if (score and score >= 55) else "#ff5252")
                st.markdown(
                    f"<div style='color:{sc};font-weight:700;font-size:1.1rem'>"
                    f"{score or '—'}"
                    f"<span style='color:#7ecdd8;font-size:.75rem'>/100</span></div>"
                    f"<div style='color:#7ecdd8;font-size:.78rem'>Fit Score</div>",
                    unsafe_allow_html=True,
                )
            with r4:
                st.markdown(
                    f"<div style='color:#e0f7fa;font-size:.8rem'>"
                    f"<b>Posted:</b> {fmt_date(job.get('posted_at',''))}</div>"
                    f"<div style='color:#e0f7fa;font-size:.8rem'>"
                    f"<b>Updated:</b> {fmt_date(job.get('updated_at',''))}</div>",
                    unsafe_allow_html=True,
                )
            with r5:
                if job.get("apply_url"):
                    st.link_button("🔗 Open Job", job["apply_url"])
            if job.get("fit_reasoning"):
                st.markdown(
                    f"<div style='color:#7ecdd8;font-size:.8rem;margin-top:8px;"
                    f"padding:8px 12px;background:#010d0f;border-radius:6px'>"
                    f"🤖 {job['fit_reasoning'][:220]}</div>",
                    unsafe_allow_html=True,
                )

# ─────────────────────────────────────────────────
# TAB 3 — NEEDS YOUR ACTION
# ─────────────────────────────────────────────────
with tab_act:
    escalated = [j for j in all_jobs if j.get("status") == "escalated"]
    st.markdown(f"### ⚠️ Needs Your Action  ·  {len(escalated)} job(s)")

    if not escalated:
        st.success("🎉 Nothing needs your attention — the pipeline handled everything!")
    else:
        st.markdown("""
        <div style="background:#1a0d00;border:1px solid #ffb30044;border-left:4px solid #ffb300;
          border-radius:8px;padding:12px 16px;color:#ffb300;font-size:.88rem;margin-bottom:20px">
          These jobs could not be fully auto-applied. Open the form, complete it yourself,
          then click <b>Mark as Applied</b> so the pipeline tracks it correctly.
        </div>
        """, unsafe_allow_html=True)

        for job in escalated:
            notes = (job.get("notes") or "").lower()
            if "captcha" in notes:
                icon, reason = "🚧", "CAPTCHA detected — must be solved by a human"
            elif "manual_only" in notes:
                icon, reason = "🔒", "Platform requires manual login (Workday / LinkedIn / Indeed)"
            elif "fill_rate" in notes:
                icon, reason = "📝", "Too few form fields found — complete manually"
            else:
                icon, reason = "⚠️", "Review and apply manually"

            st.markdown(f"""
            <div class="job-card">
              <h4>{job['title']} &nbsp; {source_badge(job.get('source',''))}</h4>
              <div class="meta">
                🏢 {job['company']} &nbsp; 📍 {job.get('location','Remote')}
                &nbsp; 🎯 Score: {job.get('fit_score','—')}/100
              </div>
              <div style="margin-top:10px;color:#ffb300;font-size:.85rem">
                {icon} <b>{reason}</b>
              </div>
            </div>
            """, unsafe_allow_html=True)

            c1, c2, c3 = st.columns([2, 2, 2])
            with c1:
                url = job.get("apply_url", "")
                if url and not url.startswith("mailto:"):
                    st.link_button("📂 Open Form", url, use_container_width=True)
                elif url.startswith("mailto:"):
                    st.markdown(
                        f"<div style='color:#7ecdd8;font-size:.82rem'>📧 {url[:60]}</div>",
                        unsafe_allow_html=True,
                    )
            with c2:
                if st.button("✅ Mark as Applied", key=f"done_{job['job_id']}", use_container_width=True):
                    store.update_status(job["job_id"], "submitted", notes="Manually submitted by Eddie")
                    st.success("Marked!")
                    st.rerun()
            with c3:
                if st.button("⏭️ Skip", key=f"skip_{job['job_id']}", use_container_width=True):
                    store.update_status(job["job_id"], "skipped")
                    st.rerun()
            st.markdown("")

# ─────────────────────────────────────────────────
# TAB 4 — APPROVE POOR FIT
# ─────────────────────────────────────────────────
with tab_poor:
    rejected = [j for j in all_jobs if j.get("status") == "rejected"]
    st.markdown(f"### 🔓 Poor Fit Jobs  ·  {len(rejected)} job(s)")
    st.markdown("""
    <div style="color:#7ecdd8;font-size:.85rem;margin-bottom:20px">
      The AI scored these below your threshold. If a role still interests you,
      click <b>Apply Anyway</b> — it will be queued for the next pipeline run.
    </div>
    """, unsafe_allow_html=True)

    if not rejected:
        st.info("No poor-fit jobs in the queue.")
    else:
        for job in rejected:
            with st.expander(
                f"{job['title']}  ·  {job['company']}  ·  Score: {job.get('fit_score','?')}/100",
                expanded=False,
            ):
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(source_badge(job.get("source","")), unsafe_allow_html=True)
                    st.markdown(
                        f"📍 {job.get('location','Remote')}  ·  🗓 {fmt_date(job.get('posted_at',''))}",
                        unsafe_allow_html=True,
                    )
                    if job.get("fit_reasoning"):
                        st.markdown(
                            f"<div style='color:#7ecdd8;font-size:.82rem;margin-top:6px'>"
                            f"🤖 {job['fit_reasoning'][:300]}</div>",
                            unsafe_allow_html=True,
                        )
                    gaps = job.get("gaps_flagged") or []
                    if isinstance(gaps, list) and gaps:
                        st.markdown(
                            f"<div style='color:#ff7070;font-size:.8rem;margin-top:4px'>"
                            f"⚡ Gaps: {', '.join(gaps[:3])}</div>",
                            unsafe_allow_html=True,
                        )
                with col_btn:
                    if st.button("⚡ Apply Anyway", key=f"app_{job['job_id']}", use_container_width=True):
                        store.approve_rejected(job["job_id"])
                        st.success("Queued!")
                        st.rerun()
                    if job.get("apply_url"):
                        st.link_button("🔗 View", job["apply_url"], use_container_width=True)

# ─────────────────────────────────────────────────
# TAB 5 — COVER LETTERS
# ─────────────────────────────────────────────────
with tab_cl:
    st.markdown("### ✉️ Cover Letters & Application Emails")
    st.markdown("""
    <div style="color:#7ecdd8;font-size:.85rem;margin-bottom:20px">
      AI-generated cover letters tailored to each role. Edit and save — your version
      will be used on the next apply attempt for that job.
    </div>
    """, unsafe_allow_html=True)

    eligible = [
        j for j in all_jobs
        if j.get("cover_letter_text") or j.get("cover_letter_path")
           or j.get("status") in ("submitted", "escalated", "approved", "pending_review", "drafted")
    ]

    if not eligible:
        st.info("Cover letters appear here after the first pipeline run processes jobs.")
    else:
        labels    = {j["job_id"]: f"{j['title']} @ {j['company']}" for j in eligible}
        chosen_id = st.selectbox(
            "Select a job",
            options=list(labels.keys()),
            format_func=lambda x: labels[x],
        )
        chosen = next((j for j in eligible if j["job_id"] == chosen_id), None)

        if chosen:
            st.markdown(f"""
            <div style="background:#021a1e;border:1px solid #00e5ff22;border-radius:10px;
              padding:14px 18px;margin-bottom:16px">
              <b style="color:#e0f7fa">{chosen['title']}</b>
              <span style="color:#7ecdd8">
                · {chosen['company']} · {chosen.get('location','Remote')}
              </span><br>
              {source_badge(chosen.get('source',''))} &nbsp;
              {status_badge(chosen.get('status',''))} &nbsp;
              <span style="color:#7ecdd8;font-size:.8rem">
                Score: {chosen.get('fit_score','—')}/100
              </span>
            </div>
            """, unsafe_allow_html=True)

            existing    = load_cover_letter(chosen)
            placeholder = (
                f"Dear Hiring Team,\n\n"
                f"I am writing to apply for the {chosen['title']} position at {chosen['company']}.\n\n"
                f"[No cover letter generated yet — run the pipeline first]\n\n"
                f"Kind regards,\nEddie Bila\neddiebila10@gmail.com"
            )
            edited = st.text_area(
                "Edit if needed — click Save to persist",
                value=existing or placeholder,
                height=340,
                key=f"cl_{chosen_id}",
            )

            s_col, o_col = st.columns([1, 3])
            with s_col:
                if st.button("💾 Save Cover Letter", use_container_width=True):
                    store.save_cover_letter(chosen_id, edited)
                    st.success("Saved! Will be used on next apply attempt.")
            with o_col:
                if chosen.get("apply_url"):
                    st.link_button("🔗 Open Application Form", chosen["apply_url"])

            if chosen.get("fit_reasoning"):
                st.markdown("---")
                st.markdown("**🤖 AI Reasoning:**")
                st.markdown(
                    f"<div style='color:#7ecdd8;font-size:.85rem'>{chosen['fit_reasoning']}</div>",
                    unsafe_allow_html=True,
                )
