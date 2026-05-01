import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{company_name} - AE Handoff Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=Sora:wght@500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        :root {{
            --bg: #f3efe6;
            --surface: rgba(255, 255, 255, 0.78);
            --surface-strong: rgba(255, 255, 255, 0.92);
            --ink: #1e2930;
            --muted: #667681;
            --line: rgba(30, 41, 48, 0.12);
            --accent: #0f766e;
            --accent-soft: rgba(15, 118, 110, 0.12);
            --danger: #b42318;
            --danger-soft: rgba(180, 35, 24, 0.12);
            --warn: #b45309;
            --warn-soft: rgba(180, 83, 9, 0.12);
            --success: #166534;
            --success-soft: rgba(22, 101, 52, 0.12);
            --shadow: 0 18px 50px rgba(37, 45, 52, 0.08);
        }}
        body {{
            font-family: 'IBM Plex Sans', sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at top left, rgba(15, 118, 110, 0.14), transparent 28%),
                radial-gradient(circle at top right, rgba(180, 83, 9, 0.10), transparent 26%),
                linear-gradient(180deg, #f6f2e9 0%, #ebe4d8 100%);
            min-height: 100vh;
            line-height: 1.55;
        }}
        .container {{
            max-width: 1440px;
            margin: 0 auto;
            padding: 32px 24px 56px;
        }}
        .hero {{
            display: grid;
            grid-template-columns: 1.3fr 0.9fr;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .panel {{
            background: var(--surface);
            border: 1px solid rgba(255, 255, 255, 0.65);
            backdrop-filter: blur(18px);
            box-shadow: var(--shadow);
            border-radius: 18px;
            padding: 24px;
        }}
        .eyebrow {{
            font-size: 12px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--muted);
            margin-bottom: 10px;
        }}
        .hero h1 {{
            font-family: 'Sora', sans-serif;
            font-size: 46px;
            line-height: 1.05;
            margin-bottom: 12px;
        }}
        .hero-subtitle {{
            max-width: 760px;
            color: var(--muted);
            font-size: 16px;
            margin-bottom: 18px;
        }}
        .score-badge {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            padding: 10px 16px;
            border-radius: 999px;
            font-weight: 700;
            margin-bottom: 18px;
        }}
        .score-badge.very-high-intent {{
            background: var(--success-soft);
            color: var(--success);
        }}
        .score-badge.high-intent {{
            background: var(--accent-soft);
            color: var(--accent);
        }}
        .score-badge.qualified {{
            background: var(--warn-soft);
            color: var(--warn);
        }}
        .score-badge.disqualified {{
            background: var(--danger-soft);
            color: var(--danger);
        }}
        .hero-stats {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
        }}
        .stat-card {{
            background: var(--surface-strong);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 14px 16px;
            min-height: 94px;
        }}
        .stat-label {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--muted);
            margin-bottom: 10px;
        }}
        .stat-value {{
            font-size: 18px;
            font-weight: 700;
        }}
        .hero-brief {{
            display: grid;
            gap: 12px;
        }}
        .signal-card {{
            padding: 18px;
            border-radius: 16px;
            border: 1px solid var(--line);
            background: linear-gradient(180deg, rgba(255,255,255,0.9), rgba(255,255,255,0.72));
        }}
        .signal-title {{
            font-family: 'Sora', sans-serif;
            font-size: 14px;
            margin-bottom: 8px;
        }}
        .signal-copy {{
            color: var(--muted);
            font-size: 15px;
        }}
        .section {{
            background: var(--surface);
            border: 1px solid rgba(255, 255, 255, 0.65);
            box-shadow: var(--shadow);
            backdrop-filter: blur(18px);
            border-radius: 18px;
            padding: 24px;
            margin-bottom: 20px;
        }}
        .section-title {{
            font-family: 'Sora', sans-serif;
            font-size: 22px;
            margin-bottom: 6px;
        }}
        .section-subtitle {{
            color: var(--muted);
            font-size: 14px;
            margin-bottom: 18px;
        }}
        .contacts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 12px;
        }}
        .contact-card {{
            background: var(--surface-strong);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 16px;
        }}
        .contact-name {{
            font-weight: 700;
            margin-bottom: 4px;
        }}
        .contact-title {{
            font-size: 14px;
            color: var(--muted);
            margin-bottom: 10px;
        }}
        .contact-email {{
            font-size: 14px;
            color: var(--accent);
            word-break: break-word;
        }}
        .dm-badge {{
            display: inline-flex;
            margin-top: 10px;
            padding: 5px 10px;
            border-radius: 999px;
            background: var(--accent-soft);
            color: var(--accent);
            font-size: 12px;
            font-weight: 700;
        }}
        .coverage-grid {{
            display: grid;
            grid-template-columns: 1.15fr 0.85fr;
            gap: 18px;
        }}
        .coverage-card {{
            background: var(--surface-strong);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 18px;
        }}
        .coverage-list {{
            display: grid;
            gap: 10px;
        }}
        .coverage-item {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            font-size: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--line);
        }}
        .coverage-item:last-child {{
            border-bottom: none;
            padding-bottom: 0;
        }}
        .coverage-label {{
            color: var(--muted);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th {{
            text-align: left;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--muted);
            padding: 0 0 12px;
        }}
        td {{
            padding: 14px 0;
            border-top: 1px solid var(--line);
            font-size: 14px;
            vertical-align: top;
        }}
        .call-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .pill {{
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }}
        .pill.trigger {{
            background: var(--accent-soft);
            color: var(--accent);
        }}
        .pill.done {{
            background: var(--success-soft);
            color: var(--success);
        }}
        .pill.waiting {{
            background: var(--warn-soft);
            color: var(--warn);
        }}
        .pill.error {{
            background: var(--danger-soft);
            color: var(--danger);
        }}
        .score-cell {{
            display: inline-flex;
            justify-content: center;
            min-width: 42px;
            padding: 8px 10px;
            border-radius: 10px;
            font-weight: 700;
        }}
        .score-0 {{ background: rgba(180, 35, 24, 0.10); color: var(--danger); }}
        .score-1 {{ background: rgba(180, 83, 9, 0.10); color: var(--warn); }}
        .score-2 {{ background: rgba(15, 118, 110, 0.10); color: var(--accent); }}
        .score-3 {{ background: rgba(22, 101, 52, 0.12); color: var(--success); }}
        .two-up {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
        }}
        .brief-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
        }}
        .brief-card {{
            background: var(--surface-strong);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 18px;
        }}
        .brief-card.span-2 {{
            grid-column: span 2;
        }}
        .brief-card-title {{
            font-family: 'Sora', sans-serif;
            font-size: 14px;
            margin-bottom: 10px;
        }}
        .brief-card-content {{
            color: var(--muted);
            font-size: 15px;
        }}
        .empty-note {{
            color: var(--muted);
            font-size: 14px;
        }}
        .footer {{
            text-align: center;
            color: var(--muted);
            font-size: 13px;
            padding-top: 8px;
        }}
        @media (max-width: 1080px) {{
            .hero,
            .coverage-grid,
            .two-up,
            .brief-grid {{
                grid-template-columns: 1fr;
            }}
            .brief-card.span-2 {{
                grid-column: auto;
            }}
            .hero-stats {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
        }}
        @media (max-width: 720px) {{
            .container {{
                padding: 18px 14px 40px;
            }}
            .hero h1 {{
                font-size: 34px;
            }}
            .hero-stats {{
                grid-template-columns: 1fr;
            }}
            table,
            thead,
            tbody,
            th,
            td,
            tr {{
                display: block;
            }}
            thead {{
                display: none;
            }}
            td {{
                border-top: 1px solid var(--line);
                padding: 12px 0;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <section class="hero">
            <div class="panel">
                <div class="eyebrow">AE Handoff Dashboard</div>
                <h1>{company_name}</h1>
                <div class="hero-subtitle">{hero_summary}</div>
                <div class="score-badge {tier_class}">{weighted_score}/10 | {qualification_tier}</div>
                <div class="hero-stats">
                    <div class="stat-card">
                        <div class="stat-label">Decision Maker</div>
                        <div class="stat-value">{dm_contact}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">SDR</div>
                        <div class="stat-value">{sdr_name}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Meeting Scheduled</div>
                        <div class="stat-value">{meeting_time}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Trigger Outcome</div>
                        <div class="stat-value">{trigger_call_outcome}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Employees</div>
                        <div class="stat-value">{employees}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Location</div>
                        <div class="stat-value">{location}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Calls In Scope</div>
                        <div class="stat-value">{calls_in_scope}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Calls Analyzed</div>
                        <div class="stat-value">{calls_analyzed}</div>
                    </div>
                </div>
            </div>

            <div class="hero-brief">
                <div class="signal-card">
                    <div class="signal-title">What AE Should Know First</div>
                    <div class="signal-copy">{pain_need}</div>
                </div>
                <div class="signal-card">
                    <div class="signal-title">Current Process</div>
                    <div class="signal-copy">{current_process}</div>
                </div>
                <div class="signal-card">
                    <div class="signal-title">Next Move</div>
                    <div class="signal-copy">{next_steps}</div>
                </div>
            </div>
        </section>

        <section class="section">
            <div class="section-title">Call Coverage</div>
            <div class="section-subtitle">This is the real scope the brief was built from, including which calls actually reached analysis.</div>
            <div class="coverage-grid">
                <div class="coverage-card">
                    <div class="coverage-list">
                        <div class="coverage-item"><span class="coverage-label">Trigger call date</span><strong>{meeting_time}</strong></div>
                        <div class="coverage-item"><span class="coverage-label">Trigger disposition</span><strong>{trigger_call_outcome}</strong></div>
                        <div class="coverage-item"><span class="coverage-label">Contacts fetched from HubSpot</span><strong>{contacts_count}</strong></div>
                        <div class="coverage-item"><span class="coverage-label">Calls in analysis set</span><strong>{calls_in_scope}</strong></div>
                        <div class="coverage-item"><span class="coverage-label">Recordings available</span><strong>{recording_coverage}</strong></div>
                        <div class="coverage-item"><span class="coverage-label">Fully analyzed calls</span><strong>{calls_analyzed}</strong></div>
                    </div>
                </div>
                <div class="coverage-card">
                    <div class="signal-title" style="margin-bottom: 8px;">Evaluation Signal</div>
                    <div class="signal-copy">{evaluating_tools}</div>
                    <div class="signal-title" style="margin-top: 18px; margin-bottom: 8px;">ICP Fit</div>
                    <div class="signal-copy">{icp_fit}</div>
                </div>
            </div>
        </section>

        <section class="section">
            <div class="section-title">Contacts</div>
            <div class="section-subtitle">HubSpot is the source of truth for company and contact context.</div>
            <div class="contacts-grid">
                {contacts_html}
            </div>
        </section>

        <section class="section">
            <div class="section-title">Call Set</div>
            <div class="section-subtitle">Trigger plus prior relevant connected or high-intent callback history.</div>
            <table>
                <thead>
                    <tr>
                        <th>Call</th>
                        <th>Disposition</th>
                        <th>Recording</th>
                        <th>Transcript</th>
                        <th>Analysis</th>
                    </tr>
                </thead>
                <tbody>
                    {calls_timeline_html}
                </tbody>
            </table>
        </section>

        <section class="two-up">
            <div class="section">
                <div class="section-title">Per-Call BANTIC</div>
                <div class="section-subtitle">Only calls that reached analysis appear here.</div>
                <table>
                    <thead>
                        <tr>
                            <th>Call Date</th>
                            <th>Budget</th>
                            <th>Authority</th>
                            <th>Need</th>
                            <th>Timeline</th>
                            <th>Impact</th>
                            <th>Current Process</th>
                            <th>Weighted</th>
                        </tr>
                    </thead>
                    <tbody>
                        {per_call_matrix_html}
                    </tbody>
                </table>
            </div>

            <div class="section">
                <div class="section-title">Best Signal By Dimension</div>
                <div class="section-subtitle">This is the best evidence the AE can carry into the takeover conversation.</div>
                <table>
                    <thead>
                        <tr>
                            <th>Dimension</th>
                            <th>Best</th>
                            <th>Evidence</th>
                            <th>Missing</th>
                        </tr>
                    </thead>
                    <tbody>
                        {consolidated_rows}
                    </tbody>
                </table>
            </div>
        </section>

        <section class="section">
            <div class="section-title">AE Handoff Brief</div>
            <div class="section-subtitle">Readable takeover notes for the next conversation, not just a score sheet.</div>
            <div class="brief-grid">
                <div class="brief-card">
                    <div class="brief-card-title">ICP Fit</div>
                    <div class="brief-card-content">{icp_fit}</div>
                </div>
                <div class="brief-card">
                    <div class="brief-card-title">Current Process</div>
                    <div class="brief-card-content">{current_process}</div>
                </div>
                <div class="brief-card">
                    <div class="brief-card-title">Evaluating Tools</div>
                    <div class="brief-card-content">{evaluating_tools}</div>
                </div>
                <div class="brief-card">
                    <div class="brief-card-title">Pain / Need</div>
                    <div class="brief-card-content">{pain_need}</div>
                </div>
                <div class="brief-card span-2">
                    <div class="brief-card-title">Recommended Next Steps</div>
                    <div class="brief-card-content">{next_steps}</div>
                </div>
            </div>
        </section>

        <div class="footer">Generated by AE Handoff Brief Agent</div>
    </div>
</body>
</html>
"""

def _format_display_date(value) -> str:
    if not value:
        return "Unknown"
    text = str(value)
    try:
        normalized = text.replace("Z", "+00:00")
        dt = __import__("datetime").datetime.fromisoformat(normalized)
        return dt.strftime("%d %b %Y, %I:%M %p")
    except ValueError:
        return text

def _status_pill(status: str, label: str = None) -> str:
    normalized = (status or "").lower()
    css_class = "waiting"
    if normalized in {"completed", "done", "approved", "revised"}:
        css_class = "done"
    elif normalized in {"failed", "error"}:
        css_class = "error"
    text = label or status or "pending"
    return f'<span class="pill {css_class}">{text}</span>'


def generate_html_brief(journey, score_result: Dict[str, Any], brief_sections: Dict[str, str]) -> str:
    """
    Generate a comprehensive HTML dashboard with all company and analysis data.
    """
    try:
        # Build contacts HTML
        contacts_html = ""
        if journey.contacts:
            for contact in journey.contacts:
                dm_badge = '<div class="dm-badge">DM</div>' if contact.is_dm else ''
                contacts_html += f'''
                <div class="contact-card">
                    <div class="contact-name">{contact.name}</div>
                    <div class="contact-title">{contact.title or "N/A"}</div>
                    <div class="contact-email">{contact.email or "N/A"}</div>
                    {dm_badge}
                </div>
                '''
        else:
            contacts_html = '<div style="grid-column: 1/-1; color: var(--text-secondary);">No contacts found</div>'

        # Build calls timeline HTML
        calls_timeline_html = ""
        calls_in_scope = len(journey.calls) if journey.calls else 0
        analyzed_calls = 0
        recordings_available = 0
        trigger_call_outcome = "Unknown"
        if journey.calls:
            for call in journey.calls:
                is_trigger_call = call.get("is_trigger_call", False)
                call_date = _format_display_date(call.get("call_date", "N/A"))
                disposition = call.get("call_outcome") or call.get("call_disposition_label", "N/A")
                recording = _status_pill("done", "Available") if call.get("recording_url") else _status_pill("waiting", "Missing")
                transcript_status = call.get("transcription_status", "pending")
                analysis_status = call.get("analysis_status", "pending")
                if call.get("recording_url"):
                    recordings_available += 1
                if analysis_status == "completed":
                    analyzed_calls += 1
                trigger_pill = '<span class="pill trigger">Trigger</span>' if is_trigger_call else ''
                if is_trigger_call:
                    trigger_call_outcome = disposition
                calls_timeline_html += f'''
                <tr>
                    <td>
                        <div>{call_date}</div>
                        <div class="call-meta">{trigger_pill}</div>
                    </td>
                    <td>{disposition}</td>
                    <td>{recording}</td>
                    <td>{_status_pill(transcript_status, transcript_status.title())}</td>
                    <td>{_status_pill(analysis_status, analysis_status.title())}</td>
                </tr>
                '''
        else:
            calls_timeline_html = '<tr><td colspan="5" class="empty-note">No calls in scope.</td></tr>'

        # Build per-call matrix HTML
        per_call_matrix_html = ""
        per_call_matrix = score_result.get("per_call_matrix", [])
        for call_data in per_call_matrix:
            scores = call_data.get("scores", {})
            weighted = call_data.get("weighted", 0)
            call_date = _format_display_date(call_data.get("date", "N/A"))

            per_call_matrix_html += f'''
            <tr>
                <td>{call_date}</td>
                <td><div class="score-cell score-{scores.get('budget', 0)}">{scores.get('budget', 0)}</div></td>
                <td><div class="score-cell score-{scores.get('authority', 0)}">{scores.get('authority', 0)}</div></td>
                <td><div class="score-cell score-{scores.get('need', 0)}">{scores.get('need', 0)}</div></td>
                <td><div class="score-cell score-{scores.get('timeline', 0)}">{scores.get('timeline', 0)}</div></td>
                <td><div class="score-cell score-{scores.get('impact', 0)}">{scores.get('impact', 0)}</div></td>
                <td><div class="score-cell score-{scores.get('current_process', 0)}">{scores.get('current_process', 0)}</div></td>
                <td style="font-weight: 600; color: var(--accent);">{weighted}</td>
            </tr>
            '''
        if not per_call_matrix_html:
            per_call_matrix_html = '<tr><td colspan="8" class="empty-note">No analyzed calls yet.</td></tr>'

        # Build consolidated rows HTML
        consolidated_rows = ""
        best_scores = score_result.get("best_scores", {})
        for dim_key, data in best_scores.items():
            label = data.get("label", "")
            score = data.get("best_score", 0)
            evidence = data.get("best_evidence", "N/A")
            if len(evidence) > 100:
                evidence = evidence[:100] + "..."
            missing = data.get("whats_missing", "")

            consolidated_rows += f'''
            <tr>
                <td>{label}</td>
                <td><div class="score-cell score-{score}">{score}/3</div></td>
                <td><em>{evidence}</em></td>
                <td>{missing}</td>
            </tr>
            '''
        if not consolidated_rows:
            consolidated_rows = '<tr><td colspan="4" class="empty-note">No consolidated scores available yet.</td></tr>'

        # Determine tier CSS class
        tier = score_result.get("qualification_tier", "Disqualified")
        tier_class = tier.lower().replace(" ", "-")
        hero_summary = (
            "This dashboard is built from the trigger Meeting Scheduled call and earlier relevant history. "
            "It is designed to help the AE separate confirmed signal from what is still missing."
        )

        # Format template
        html = HTML_TEMPLATE.format(
            company_name=journey.company.name,
            dm_contact=journey.dm_contact.name if journey.dm_contact else "UNKNOWN",
            sdr_name=journey.sdr_name or "Unknown",
            meeting_time=_format_display_date(journey.scheduled_meeting_time) if journey.scheduled_meeting_time else "Unknown",
            employees=journey.company.employees or "UNKNOWN",
            location=journey.company.location or "UNKNOWN",
            weighted_score=score_result.get("weighted_score", 0),
            qualification_tier=tier,
            tier_class=tier_class,
            hero_summary=hero_summary,
            trigger_call_outcome=trigger_call_outcome,
            calls_in_scope=calls_in_scope,
            calls_analyzed=analyzed_calls,
            contacts_count=len(journey.contacts or []),
            recording_coverage=f"{recordings_available}/{calls_in_scope}",
            contacts_html=contacts_html,
            calls_timeline_html=calls_timeline_html,
            per_call_matrix_html=per_call_matrix_html,
            consolidated_rows=consolidated_rows,
            icp_fit=brief_sections.get("icp_fit", "N/A"),
            current_process=brief_sections.get("current_process", "N/A"),
            evaluating_tools=brief_sections.get("evaluating_tools", "N/A"),
            pain_need=brief_sections.get("pain_need", "N/A"),
            next_steps=brief_sections.get("next_steps", "N/A"),
        )

        return html

    except Exception as e:
        logger.error(f"Error generating HTML brief: {e}")
        return f"<html><body>Error generating dashboard: {e}</body></html>"


def save_html_brief(company_name: str, html_content: str) -> str:
    """Save HTML brief to dashboards directory."""
    try:
        os.makedirs("dashboards", exist_ok=True)
        safe_name = company_name.replace("/", "_").replace(" ", "_")
        filename = f"dashboards/{safe_name}_dashboard.html"
        abs_path = os.path.abspath(filename)
        with open(abs_path, "w") as f:
            f.write(html_content)
        logger.info(f"✓ HTML dashboard saved: {abs_path}")
        return abs_path
    except Exception as e:
        logger.error(f"Error saving HTML brief: {e}")
        return None
