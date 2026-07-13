"""
app/review_app.py — WEB CareerOS™ Live Dashboard  (v3 — fixed)

Fixes applied vs v2:
  • HTML-escape all dynamic values before injecting into st.markdown HTML
    (raw job titles/companies with <> or & were breaking the entire tab → blank screen)
  • Fix Refresh button to clear BOTH st.cache_data AND st.cache_resource
  • Clear st.cache_data after every DB write so st.rerun() shows fresh data
    (buttons appeared to do nothing because cached stale data was returned)
  • Load logo as base64 so it works on Streamlit Cloud even if git-add was missed
  • Wrap data loading in try/except so errors surface instead of going blank
"""

from __future__ import annotations

import base64
import html as _html
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_queue.store import JobQueueStore
import config.settings as settings

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="WEB CareerOS",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Helper: always HTML-escape dynamic data before injecting into HTML ────────
def h(value) -> str:
    """Escape a value for safe injection into an HTML string."""
    return _html.escape(str(value) if value is not None else "")


# ── Brand CSS ────────────────────────────────────────────────────────────────
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

  .block-container { padding-top: 0.6rem !important; padding-bottom: 1rem !important; }
  #MainMenu, footer, header { visibility: hidden; }

  html, body, .stApp { background: var(--web-dark) !important; }
  .stApp { color: var(--web-white); }
  h1, h2, h3, h4, h5, h6 { color: var(--web-cyan) !important; }

  [data-testid="stSidebar"] {
    background: linear-gradient(180deg,#010f12 0%,#010d0f 100%) !important;
    border-right: 1px solid #00e5ff1a;
  }
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] p { color: var(--web-muted) !important; }

  .stTabs [data-baseweb="tab-list"] {
    background: var(--web-card);
    border-radius: 10px;
    padding: 4px;
    gap: 4px;
    border: 1px solid #00e5ff15;
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
    width: 100%;
  }
  .stButton > button:hover {
    background: var(--web-cyan) !important;
    color: var(--web-dark) !important;
  }
  .stDownloadButton > button {
    background: linear-gradient(135deg,#00bfa5,#00838f) !important;
    border: none !important;
    color: white !important;
    font-weight: 700;
    border-radius: 8px;
    width: 100%;
  }

  .badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .04em;
  }

  .stat-bar {
    background: var(--web-card);
    border: 1px solid #00e5ff18;
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 8px;
  }
  .stat-bar .num { font-size: 1.7rem; font-weight: 800; color: var(--web-cyan); }
  .stat-bar .lbl {
    font-size: .7rem;
    color: var(--web-muted);
    text-transform: uppercase;
    letter-spacing: .1em;
    margin-top: 2px;
  }

  .job-table { width: 100%; border-collapse: collapse; margin-top: 6px; }
  .job-table thead tr {
    background: #021a1e;
    color: #7ecdd8;
    font-size: .75rem;
    text-transform: uppercase;
    letter-spacing: .08em;
  }
  .job-table thead th {
    padding: 10px 12px;
    text-align: left;
    border-bottom: 1px solid #00e5ff22;
    font-weight: 700;
  }
  .job-table tbody tr { border-bottom: 1px solid #00e5ff0d; transition: background .15s; }
  .job-table tbody tr:hover { background: #021a1e88; }
  .job-table tbody td { padding: 10px 12px; font-size: .85rem; vertical-align: middle; }

  .job-table .role { color: #e0f7fa; font-weight: 600; }
  .job-table .company { color: #7ecdd8; font-size: .8rem; }
  .job-table .score-hi { color: #00c853; font-weight: 700; }
  .job-table .score-md { color: #ffb300; font-weight: 700; }
  .job-table .score-lo { color: #ff5252; font-weight: 700; }

  .action-card {
    background: var(--web-card);
    border: 1px solid #ffb30033;
    border-left: 4px solid #ffb300;
    border-radius: 10px;
    padding: 16px 18px;
    margin-bottom: 8px;
  }
  .action-card .role { color: #e0f7fa; font-size: 1rem; font-weight: 700; }
  .action-card .meta { color: #7ecdd8; font-size: .82rem; margin-top: 3px; }
  .action-card .reason { color: #ffb300; font-size: .84rem; margin-top: 8px; }

  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: var(--web-dark); }
  ::-webkit-scrollbar-thumb { background: #00e5ff44; border-radius: 4px; }
  hr { border-color: #00e5ff18 !important; }

  .stTextInput input, .stSelectbox > div > div {
    background: var(--web-card) !important;
    color: var(--web-white) !important;
    border: 1px solid #00e5ff33 !important;
    border-radius: 8px !important;
  }
  .stSelectbox label { color: var(--web-muted) !important; font-size: .8rem !important; }
  .stTextInput label { color: var(--web-muted) !important; font-size: .8rem !important; }

  .info-box {
    background: #001f22;
    border: 1px solid #00e5ff22;
    border-left: 4px solid #00e5ff;
    border-radius: 8px;
    padding: 12px 16px;
    color: #7ecdd8;
    font-size: .85rem;
    margin-bottom: 18px;
  }
</style>
""", unsafe_allow_html=True)

# ── Constants ────────────────────────────────────────────────────────────────
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
    "email":          "#00bfa5",
}

STATUS_CFG = {
    "submitted":      ("✅ Auto-Applied",   "#00c853"),
    "escalated":      ("⚠️ Needs You",       "#ffb300"),
    "rejected":       ("❌ Poor Fit",         "#ff5252"),
    "approved":       ("🟢 Queued",           "#00bfa5"),
    "new":            ("🔵 New",              "#607d8b"),
    "scored":         ("🟡 Scored",           "#ffd740"),
    "failed":         ("💥 Failed",            "#e040fb"),
    "skipped":        ("⏭️ Skipped",          "#546e7a"),
    "pending_review": ("👁 In Review",        "#7ecdd8"),
    "drafted":        ("📝 Drafted",          "#7ecdd8"),
}


def source_badge(source: str) -> str:
    src = h(source)
    c = SOURCE_COLORS.get(source, "#7ecdd8")
    return f'<span class="badge" style="background:{c}22;color:{c};border:1px solid {c}44">{src.upper()}</span>'


def status_badge(status: str) -> str:
    label, c = STATUS_CFG.get(status, (status.upper(), "#7ecdd8"))
    return f'<span class="badge" style="background:{c}22;color:{c};border:1px solid {c}44">{_html.escape(label)}</span>'


def score_class(score) -> str:
    if not score:
        return "score-md"
    if score >= 70:
        return "score-hi"
    if score >= 50:
        return "score-md"
    return "score-lo"


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


def _logo_html() -> str | None:
    """Return an <img> tag with the logo embedded as base64, or None if not found."""
    logo_path = Path(__file__).parent / "assets" / "web_logo.png"
    if logo_path.exists():
        try:
            b64 = base64.b64encode(logo_path.read_bytes()).decode()
            return (
                f'<img src="data:image/png;base64,{b64}" '
                f'style="width:90px;border-radius:10px;display:block;margin:0 auto 8px auto" />'
            )
        except Exception:
            pass
    return None


# ── Data loader ──────────────────────────────────────────────────────────────
@st.cache_resource
def get_store():
    return JobQueueStore(settings.QUEUE_DB_PATH)


@st.cache_data(ttl=300)
def _load_jobs_cached():
    store  = get_store()
    jobs   = store.get_all_jobs(limit=2000)
    counts = store.counts_by_status()
    src    = store.counts_by_source()
    return jobs, counts, src


def load_data():
    jobs, counts, src = _load_jobs_cached()
    store = get_store()
    return store, jobs, counts


def _refresh_data():
    """Clear the data cache so next run fetches fresh rows from SQLite.
    NOTE: Do NOT clear st.cache_resource -- that holds the SQLite store
    singleton. Destroying it on Streamlit Cloud causes a blank-screen hang
    on the subsequent st.rerun(). Clearing cache_data is sufficient.
    """
    st.cache_data.clear()


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    # ── Logo ──────────────────────────────────────────────────
    logo_tag = _logo_html()
    if logo_tag:
        st.markdown(logo_tag, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#021a1e,#010f12);
          border:1px solid #00e5ff33;border-radius:14px;
          padding:20px 16px;text-align:center;margin-bottom:4px">
          <div style="font-size:32px;font-weight:900;color:#00e5ff;
            letter-spacing:8px;font-family:'Segoe UI',sans-serif;
            text-shadow:0 0 20px #00e5ff66">WEB</div>
          <div style="font-size:9px;color:#7ecdd8;letter-spacing:5px;
            text-transform:uppercase;margin-top:2px;opacity:.8">CareerOS™</div>
          <div style="width:40px;height:2px;background:linear-gradient(90deg,transparent,#00e5ff,transparent);
            margin:8px auto 0"></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div style="display:flex;align-items:center;gap:8px;
      margin:10px 0 14px;padding:8px 12px;
      background:#021a1e;border-radius:8px;border:1px solid #00e5ff18">
      <span style="width:8px;height:8px;background:#00c853;border-radius:50%;
        display:inline-block;box-shadow:0 0 8px #00c853;flex-shrink:0"></span>
      <span style="color:#7ecdd8;font-size:.78rem;font-weight:600;
        letter-spacing:.06em">LIVE PIPELINE · ACTIVE</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Load data with error handling ──────────────────────────
    try:
        store, all_jobs, counts = load_data()
        _, _, src_counts_sidebar = _load_jobs_cached()
        data_ok = True
    except Exception as _e:
        st.error(f"⚠️ Could not load pipeline data: {_e}")
        store, all_jobs, counts, src_counts_sidebar = None, [], {}, {}
        data_ok = False

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
    <div class="stat-bar" style="border-color:#00c85322">
      <div class="num" style="color:#00c853">{n_submitted}</div>
      <div class="lbl">Auto-Applied For You</div>
    </div>
    <div class="stat-bar" style="border-color:#ffb30022">
      <div class="num" style="color:#ffb300">{n_escalated}</div>
      <div class="lbl">Need Your Attention</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="stat-bar" style="border-color:#ff525222">
      <div class="num" style="color:#ff5252">{n_rejected}</div>
      <div class="lbl">Poor Fit (Override Available)</div>
    </div>
    <div class="stat-bar" style="border-color:#00bfa522">
      <div class="num" style="color:#00bfa5">{n_approved}</div>
      <div class="lbl">Queued · Next Run</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # FIX: clear BOTH caches so refresh actually reloads fresh data from DB
    if st.button("🔄  Refresh Dashboard", use_container_width=True):
        _refresh_data()
        st.rerun()

    if data_ok:
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
        except Exception:
            pass

    st.markdown(
        f"<div style='color:#2a5a63;font-size:.72rem;text-align:center;"
        f"margin-top:10px;padding-top:10px;border-top:1px solid #00e5ff12'>"
        f"🕐 Last refreshed {datetime.now().strftime('%H:%M')} · "
        f"Runs daily 07:00 SAST</div>",
        unsafe_allow_html=True,
    )


# ============================================================
# MAIN HEADER
# ============================================================
h_col, _ = st.columns([6, 1])
with h_col:
    st.markdown("""
    <div style="padding-bottom:10px;border-bottom:1px solid #00e5ff18;margin-bottom:14px">
      <div style="display:flex;align-items:center;gap:12px">
        <span style="font-size:1.8rem">🚀</span>
        <div>
          <div style="font-size:1.6rem;font-weight:900;color:#00e5ff;
            line-height:1;letter-spacing:1px">WEB CareerOS™</div>
          <div style="color:#7ecdd8;font-size:.8rem;margin-top:2px">
            Autonomous Job Application Pipeline — applying on your behalf, 24/7
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

if n_escalated:
    st.warning(
        f"🔔 **{n_escalated} job(s) need your manual attention** — check the **Needs Your Action** tab.",
        icon="⚠️",
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


# ─────────────────────────────────────────────────────────────
# TAB 1 — OVERVIEW
# ─────────────────────────────────────────────────────────────
with tab_ov:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Jobs Found",   total)
    c2.metric("Auto-Applied", n_submitted,  help="System submitted these on your behalf")
    c3.metric("Need You",     n_escalated,  help="CAPTCHA / login required / form incomplete")
    c4.metric("Poor Fit",     n_rejected,   help="Scored below threshold — you can override")
    c5.metric("In Queue",     n_approved,   help="Scored well — applying on next run")

    st.markdown("---")

    _, _, src_counts = _load_jobs_cached()
    if src_counts:
        st.markdown("### 🌐 Jobs by Source")
        cols = st.columns(min(len(src_counts), 5))
        for i, (src, cnt) in enumerate(sorted(src_counts.items(), key=lambda x: -x[1])):
            color = SOURCE_COLORS.get(src, "#7ecdd8")
            with cols[i % 5]:
                st.markdown(f"""
                <div style="background:#021a1e;border:1px solid {color}33;
                  border-top:3px solid {color};border-radius:10px;
                  padding:14px 16px;margin-bottom:8px;text-align:center">
                  <div style="font-size:1.8rem;font-weight:800;color:{color}">{cnt}</div>
                  <div style="font-size:.72rem;color:#7ecdd8;text-transform:uppercase;
                    letter-spacing:.07em;margin-top:2px">{h(src)}</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🕐 Recent Activity")

    recent = sorted(all_jobs, key=lambda j: j.get("updated_at", ""), reverse=True)[:15]
    rows = ""
    for job in recent:
        sl, sc = STATUS_CFG.get(job.get("status", ""), (job.get("status", "").upper(), "#7ecdd8"))
        rows += f"""
        <tr>
          <td><div class="role">{h(job['title'])}</div>
              <div class="company">{h(job['company'])}</div></td>
          <td>{source_badge(job.get('source', ''))}</td>
          <td><span class="badge" style="background:{sc}22;color:{sc};border:1px solid {sc}44">{_html.escape(sl)}</span></td>
          <td class="{score_class(job.get('fit_score'))}">{job.get('fit_score', '—')}</td>
          <td style="color:#7ecdd8;font-size:.8rem">{fmt_date(job.get('updated_at', ''))}</td>
        </tr>"""

    st.markdown(f"""
    <table class="job-table">
      <thead><tr>
        <th>Role / Company</th><th>Source</th><th>Status</th>
        <th>Score</th><th>Date</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# TAB 2 — ALL JOBS
# ─────────────────────────────────────────────────────────────
with tab_all:
    f1, f2, f3, f4 = st.columns([3, 2, 2, 2])
    with f1:
        q = st.text_input("🔍 Search", placeholder="title, company…", label_visibility="collapsed")
    with f2:
        status_f = st.selectbox("Status", ["All"] + sorted({j["status"] for j in all_jobs}), label_visibility="collapsed")
    with f3:
        source_f = st.selectbox("Source", ["All"] + sorted({j.get("source", "") for j in all_jobs}), label_visibility="collapsed")
    with f4:
        remote_f = st.selectbox("Location", ["All", "Remote Only", "On-site Only"], label_visibility="collapsed")

    filtered = all_jobs
    if q:
        ql = q.lower()
        filtered = [j for j in filtered
                    if ql in j.get("title", "").lower() or ql in j.get("company", "").lower()]
    if status_f != "All":
        filtered = [j for j in filtered if j.get("status") == status_f]
    if source_f != "All":
        filtered = [j for j in filtered if j.get("source") == source_f]
    if remote_f == "Remote Only":
        filtered = [j for j in filtered if j.get("is_remote")]
    elif remote_f == "On-site Only":
        filtered = [j for j in filtered if not j.get("is_remote")]

    st.markdown(
        f"<div style='color:#7ecdd8;font-size:.78rem;margin-bottom:8px'>"
        f"Showing <b style='color:#00e5ff'>{len(filtered)}</b> of {len(all_jobs)} jobs</div>",
        unsafe_allow_html=True,
    )

    rows = ""
    for job in filtered[:300]:
        sl, sc = STATUS_CFG.get(job.get("status", ""), (job.get("status", "").upper(), "#7ecdd8"))
        loc = "🌐 Remote" if job.get("is_remote") else f"📍 {h(job.get('location') or 'N/A')}"
        score = job.get("fit_score")
        scls  = score_class(score)
        url   = h(job.get("apply_url", ""))
        action_td = (
            f'<a href="{url}" target="_blank" style="color:#00e5ff;font-size:.8rem;'
            f'text-decoration:none;padding:4px 10px;border:1px solid #00e5ff44;'
            f'border-radius:6px;white-space:nowrap">🔗 Open</a>'
            if url else "—"
        )
        reasoning = h((job.get("fit_reasoning") or "")[:120])
        reason_td = (
            f'<div style="color:#7ecdd8;font-size:.76rem;margin-top:3px">{reasoning}</div>'
            if reasoning else ""
        )
        rows += f"""
        <tr>
          <td>
            <div class="role">{h(job['title'])}</div>
            <div class="company">{h(job['company'])}</div>
            {reason_td}
          </td>
          <td>{source_badge(job.get('source', ''))}<br>
              <span style="color:#7ecdd8;font-size:.75rem">{loc}</span></td>
          <td><span class="badge" style="background:{sc}22;color:{sc};border:1px solid {sc}44">{_html.escape(sl)}</span></td>
          <td class="{scls}" style="text-align:center">{score or '—'}</td>
          <td style="color:#7ecdd8;font-size:.78rem">{fmt_date(job.get('posted_at', ''))}</td>
          <td>{action_td}</td>
        </tr>"""

    st.markdown(f"""
    <table class="job-table">
      <thead><tr>
        <th style="min-width:200px">Role / Company</th>
        <th>Source · Location</th>
        <th>Status</th>
        <th style="text-align:center">Score</th>
        <th>Posted</th>
        <th>Action</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# TAB 3 — NEEDS YOUR ACTION
# ─────────────────────────────────────────────────────────────
with tab_act:
    escalated = [j for j in all_jobs if j.get("status") == "escalated"]

    st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
      <div>
        <h3 style="margin:0;color:#ffb300">⚠️ Needs Your Action</h3>
        <div style="color:#7ecdd8;font-size:.82rem;margin-top:2px">
          {len(escalated)} job(s) the bot couldn't fully auto-submit
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not escalated:
        st.success("🎉 Nothing needs your attention — the pipeline handled everything automatically!")

    else:
        st.markdown("""
        <div class="info-box">
          Open each job form, complete it manually, then click <b>✅ Mark as Applied</b>
          so the dashboard tracks it. Or skip if not interested.
        </div>
        """, unsafe_allow_html=True)

        for job in escalated:
            notes = (job.get("notes") or "").lower()
            if "captcha" in notes:
                icon, reason = "🚧", "CAPTCHA detected — must be solved by a human"
                reason_color = "#ff7043"
            elif "manual_only" in notes:
                icon, reason = "🔒", "Platform requires manual login (Workday / LinkedIn / Indeed)"
                reason_color = "#ffb300"
            elif "fill_rate" in notes:
                icon, reason = "📝", "Form partially completed — please finish and submit"
                reason_color = "#7ecdd8"
            else:
                icon, reason = "⚠️", "Needs manual review and submission"
                reason_color = "#ffb300"

            score = job.get("fit_score")
            scls  = score_class(score)

            st.markdown(f"""
            <div class="action-card">
              <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                  <div class="role">{h(job['title'])}</div>
                  <div class="meta">
                    🏢 {h(job['company'])} &nbsp;·&nbsp;
                    📍 {h(job.get('location') or 'Remote')} &nbsp;·&nbsp;
                    {source_badge(job.get('source', ''))} &nbsp;·&nbsp;
                    <span class="{scls}">Score: {score or '—'}/100</span>
                  </div>
                </div>
              </div>
              <div class="reason">{icon} {_html.escape(reason)}</div>
              {f'<div style="color:#7ecdd8;font-size:.8rem;margin-top:6px;font-style:italic">{h(job["fit_reasoning"][:200])}</div>' if job.get("fit_reasoning") else ''}
            </div>
            """, unsafe_allow_html=True)

            url = job.get("apply_url", "")
            c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
            with c1:
                if url and not url.startswith("mailto:"):
                    st.link_button("📂 Open Application Form", url, use_container_width=True)
                elif url.startswith("mailto:"):
                    st.markdown(
                        f"<div style='color:#7ecdd8;font-size:.82rem;padding:8px 0'>📧 {h(url)}</div>",
                        unsafe_allow_html=True,
                    )
            with c2:
                # FIX: clear data cache before rerun so UI reflects the DB change
                if st.button("✅ Mark as Applied", key=f"done_{job['job_id']}", use_container_width=True):
                    try:
                        store.update_status(job["job_id"], "submitted", notes="Manually submitted by Eddie")
                        st.cache_data.clear()
                        st.success("✅ Marked as applied!")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Failed to update: {ex}")
            with c3:
                if st.button("⚡ Force Auto-Apply", key=f"force_{job['job_id']}", use_container_width=True):
                    try:
                        store.update_status(job["job_id"], "approved", notes="Force-approved by Eddie")
                        st.cache_data.clear()
                        st.info("Queued for next pipeline run.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Failed to update: {ex}")
            with c4:
                if st.button("⏭️ Skip / Not Interested", key=f"skip_{job['job_id']}", use_container_width=True):
                    try:
                        store.update_status(job["job_id"], "skipped")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Failed to update: {ex}")
            st.markdown("<hr style='margin:8px 0'>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# TAB 4 — APPROVE POOR FIT
# ─────────────────────────────────────────────────────────────
with tab_poor:
    rejected = [j for j in all_jobs if j.get("status") == "rejected"]

    st.markdown(f"""
    <div style="margin-bottom:14px">
      <h3 style="margin:0;color:#ff5252">🔓 Approve Poor Fit Jobs</h3>
      <div style="color:#7ecdd8;font-size:.82rem;margin-top:2px">
        {len(rejected)} job(s) scored below threshold — review and override if you want to apply
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not rejected:
        st.info("No poor-fit jobs to review.")
    else:
        ba1, ba2, _ = st.columns([2, 2, 4])
        with ba1:
            if st.button("⚡ Apply to ALL Poor Fit Jobs", use_container_width=True):
                try:
                    for job in rejected:
                        store.approve_rejected(job["job_id"])
                    st.cache_data.clear()
                    st.success(f"Queued {len(rejected)} jobs!")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Failed: {ex}")

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        for job in rejected:
            score = job.get("fit_score")
            scls  = score_class(score)
            gaps  = job.get("gaps_flagged") or []
            if isinstance(gaps, str):
                try:
                    gaps = json.loads(gaps)
                except Exception:
                    gaps = [gaps]

            reasoning = h((job.get("fit_reasoning") or "")[:250])
            gaps_html = (
                f'<div style="color:#ff7070;font-size:.78rem;margin-top:4px">'
                f'⚡ Gaps: {", ".join(h(g) for g in gaps[:4])}</div>'
                if gaps else ""
            )

            with st.expander(
                f"{'🔴' if (score or 0) < 40 else '🟡'} "
                f"{job['title']}  ·  {job['company']}  ·  "
                f"Score: {score or '?'}/100",
                expanded=False,
            ):
                left, right = st.columns([4, 1])
                with left:
                    st.markdown(
                        f"{source_badge(job.get('source', ''))}&nbsp;"
                        f"<span style='color:#7ecdd8;font-size:.8rem'>"
                        f"📍 {h(job.get('location', 'Remote'))} &nbsp;·&nbsp; "
                        f"🗓 {fmt_date(job.get('posted_at', ''))}</span>",
                        unsafe_allow_html=True,
                    )
                    if reasoning:
                        st.markdown(
                            f"<div style='color:#7ecdd8;font-size:.82rem;"
                            f"margin-top:6px;padding:8px 10px;"
                            f"background:#010d0f;border-radius:6px'>"
                            f"🤖 {reasoning}</div>{gaps_html}",
                            unsafe_allow_html=True,
                        )

                with right:
                    if st.button("⚡ Apply Anyway", key=f"app_{job['job_id']}", use_container_width=True):
                        try:
                            store.approve_rejected(job["job_id"])
                            st.cache_data.clear()
                            st.success("Queued!")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Failed: {ex}")
                    if job.get("apply_url"):
                        st.link_button("🔗 View Job", job["apply_url"], use_container_width=True)
                    if st.button("🗑 Remove", key=f"rm_{job['job_id']}", use_container_width=True):
                        try:
                            store.update_status(job["job_id"], "skipped")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Failed: {ex}")


# ─────────────────────────────────────────────────────────────
# TAB 5 — COVER LETTERS
# ─────────────────────────────────────────────────────────────
with tab_cl:
    st.markdown("### ✉️ Cover Letters & Application Emails")
    st.markdown("""
    <div class="info-box">
      AI-generated cover letters tailored to each role. Edit and save —
      your version will be used on the next apply attempt for that job.
    </div>
    """, unsafe_allow_html=True)

    eligible = [
        j for j in all_jobs
        if j.get("cover_letter_text") or j.get("cover_letter_path")
           or j.get("status") in ("submitted", "escalated", "approved", "pending_review", "drafted")
    ]

    if not eligible:
        st.info("Cover letters appear here after the pipeline processes jobs with auto-cover-letter enabled.")
    else:
        labels    = {j["job_id"]: f"{j['title']} @ {j['company']} · {j.get('status', '')}" for j in eligible}
        chosen_id = st.selectbox(
            "Select a job",
            options=list(labels.keys()),
            format_func=lambda x: labels[x],
        )
        chosen = next((j for j in eligible if j["job_id"] == chosen_id), None)

        if chosen:
            score = chosen.get("fit_score")
            sl, sc = STATUS_CFG.get(chosen.get("status", ""), (chosen.get("status", "").upper(), "#7ecdd8"))
            st.markdown(f"""
            <div style="background:#021a1e;border:1px solid #00e5ff22;border-radius:10px;
              padding:14px 18px;margin-bottom:16px">
              <b style="color:#e0f7fa;font-size:1rem">{h(chosen['title'])}</b>
              <span style="color:#7ecdd8"> · {h(chosen['company'])} · {h(chosen.get('location', 'Remote'))}</span><br>
              <div style="margin-top:6px">
                {source_badge(chosen.get('source', ''))} &nbsp;
                <span class="badge" style="background:{sc}22;color:{sc};border:1px solid {sc}44">{_html.escape(sl)}</span>
                &nbsp;
                <span class="{score_class(score)}" style="font-size:.85rem;font-weight:700">
                  Score: {score or '—'}/100
                </span>
              </div>
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
                "Edit cover letter:",
                value=existing or placeholder,
                height=340,
                key=f"cl_{chosen_id}",
            )

            s1, s2, s3 = st.columns([2, 2, 4])
            with s1:
                if st.button("💾 Save Cover Letter", use_container_width=True):
                    try:
                        store.save_cover_letter(chosen_id, edited)
                        st.cache_data.clear()
                        st.success("Saved! Will be used on next apply attempt.")
                    except Exception as ex:
                        st.error(f"Failed to save: {ex}")
            with s2:
                if chosen.get("apply_url"):
                    st.link_button("🔗 Open Application Form", chosen["apply_url"], use_container_width=True)

            if chosen.get("fit_reasoning"):
                st.markdown("---")
                st.markdown("**🤖 AI Reasoning:**")
                st.markdown(
                    f"<div style='color:#7ecdd8;font-size:.85rem;padding:10px 14px;"
                    f"background:#010d0f;border-radius:8px'>{h(chosen['fit_reasoning'])}</div>",
                    unsafe_allow_html=True,
                )
