"""
app/report.py — Daily HTML report (WEB Brand Edition)
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path


def write_html_report(store, settings, counts: dict, run_start: datetime) -> None:
    queue           = store.counts_by_status()
    submitted_today = store.get_by_status("submitted")
    escalated       = store.get_by_status("escalated")
    rejected        = store.get_by_status("rejected")
    total_found     = sum(queue.values())

    def job_rows(jobs, show_reason=False):
        if not jobs:
            return "<tr><td colspan='4' style='color:#7ecdd8;padding:12px;text-align:center'>None</td></tr>"
        rows = ""
        for j in jobs:
            reason = (j.get("notes") or "")[:100]
            score  = j.get("fit_score", "—")
            rows += (
                f"<tr>"
                f"<td><b style='color:#e0f7fa'>{j['title']}</b></td>"
                f"<td style='color:#7ecdd8'>{j['company']}</td>"
                f"<td><a href='{j['apply_url']}' target='_blank' style='color:#00e5ff'>Apply Link</a></td>"
                f"<td style='color:#7ecdd8'>{score}/100</td>"
                + (f"<td style='color:#ff7070;font-size:.8rem'>{reason}</td>" if show_reason else "")
                + "</tr>"
            )
        return rows

    n_submitted = counts.get("submitted", 0)
    n_escalated = len(escalated)
    n_rejected  = len(rejected)

    if n_escalated == 0 and n_submitted > 0:
        headline = f"✅ I applied to {n_submitted} jobs for you today. Nothing needs your attention."
        headline_color = "#00bfa5"
    elif n_escalated > 0:
        headline = f"⚠️ I applied to {n_submitted} jobs. {n_escalated} need your help — I couldn't access the form."
        headline_color = "#ffb300"
    else:
        headline = "📋 Pipeline ran — no applications made today. Queue is building."
        headline_color = "#7ecdd8"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Pipeline — Daily Report</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #010d0f;
    color: #e0f7fa;
    padding: 32px 20px;
  }}
  .container {{ max-width: 860px; margin: 0 auto; }}

  /* Header */
  .header {{ margin-bottom: 28px; }}
  .header h1 {{ font-size: 1.6rem; font-weight: 800; color: #00e5ff; }}
  .header .date {{ color: #7ecdd8; font-size: .85rem; margin-top: 4px; }}

  /* Headline */
  .headline {{
    background: #021a1e;
    border: 1px solid #00e5ff33;
    border-left: 5px solid {headline_color};
    border-radius: 10px;
    padding: 18px 22px;
    font-size: 1.1rem;
    font-weight: 600;
    color: {headline_color};
    margin-bottom: 28px;
  }}

  /* Stat cards */
  .cards {{ display: flex; gap: 14px; margin-bottom: 32px; flex-wrap: wrap; }}
  .card {{
    flex: 1; min-width: 130px;
    background: #021a1e;
    border: 1px solid #00e5ff22;
    border-radius: 12px;
    padding: 18px;
    text-align: center;
  }}
  .card .num {{ font-size: 2.4rem; font-weight: 800; color: #00e5ff; line-height: 1; }}
  .card .lbl {{ font-size: .75rem; color: #7ecdd8; margin-top: 6px; text-transform: uppercase; letter-spacing: .08em; }}

  /* Tables */
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 32px; }}
  th {{
    background: #021a1e;
    color: #00e5ff;
    padding: 10px 14px;
    text-align: left;
    font-size: .8rem;
    text-transform: uppercase;
    letter-spacing: .06em;
    border-bottom: 1px solid #00e5ff33;
  }}
  td {{ padding: 10px 14px; border-bottom: 1px solid #00e5ff11; font-size: .9rem; vertical-align: top; }}
  tr:hover td {{ background: #021a1e88; }}

  h2 {{ font-size: 1rem; color: #00e5ff; margin: 28px 0 10px; text-transform: uppercase; letter-spacing: .08em; }}

  /* Escalation notice */
  .notice {{
    background: #1a0d00;
    border: 1px solid #ffb30055;
    border-left: 4px solid #ffb300;
    border-radius: 8px;
    padding: 14px 18px;
    color: #ffb300;
    font-size: .9rem;
    margin-bottom: 24px;
  }}
  .notice code {{
    background: #021a1e;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: .85rem;
    color: #00e5ff;
  }}

  /* Footer */
  .footer {{ color: #3d7a85; font-size: .78rem; margin-top: 40px; text-align: center; }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>🚀 Eddie's Job Pipeline</h1>
    <div class="date">Daily Report · {run_start.strftime('%A, %d %B %Y at %H:%M')} SAST</div>
  </div>

  <div class="headline">{headline}</div>

  <div class="cards">
    <div class="card"><div class="num">{total_found}</div><div class="lbl">Jobs Found</div></div>
    <div class="card"><div class="num">{n_submitted}</div><div class="lbl">Applied For You</div></div>
    <div class="card"><div class="num">{n_escalated}</div><div class="lbl">Need Your Help</div></div>
    <div class="card"><div class="num">{n_rejected}</div><div class="lbl">Poor Fit</div></div>
    <div class="card"><div class="num">{queue.get('approved', 0)}</div><div class="lbl">In Queue</div></div>
  </div>

  {"<div class='notice'>⚠️ <b>" + str(n_escalated) + " application(s) need you</b> — the system couldn't access the form. Run <code>streamlit run app/review_app.py</code> and check the <b>Needs Your Action</b> tab.</div>" if n_escalated else ""}

  <h2>✅ Applied on Your Behalf Today ({len(submitted_today)})</h2>
  <table>
    <tr><th>Job Title</th><th>Company</th><th>Link</th><th>Score</th></tr>
    {job_rows(submitted_today)}
  </table>

  <h2>⚠️ Need Your Action ({n_escalated})</h2>
  <table>
    <tr><th>Job Title</th><th>Company</th><th>Link</th><th>Score</th><th>Reason</th></tr>
    {job_rows(escalated, show_reason=True)}
  </table>

  <h2>📊 Full Queue</h2>
  <table>
    <tr><th>Status</th><th>Count</th></tr>
    {"".join(f"<tr><td style='color:#e0f7fa'>{k.replace('_',' ').title()}</td><td style='color:#00e5ff'>{v}</td></tr>" for k, v in sorted(queue.items()))}
  </table>

  <div class="footer">
    Generated by Eddie's Autonomous Job Pipeline · {run_start.strftime('%Y-%m-%d %H:%M')}
  </div>

</div>
</body>
</html>"""

    report_path = Path(settings.REPORT_PATH)
    report_path.write_text(html, encoding="utf-8")
