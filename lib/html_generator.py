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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Outfit:wght@500;700&display=swap" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent: #38bdf8;
            --success: #22c55e;
            --warning: #eab308;
            --danger: #ef4444;
            --border: #334155;
        }}
        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            line-height: 1.6;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }}
        .header {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 2rem;
            margin-bottom: 2rem;
        }}
        .header-title {{
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 1rem;
            color: var(--accent);
        }}
        .header-meta {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
            margin-bottom: 1.5rem;
        }}
        .meta-item {{
            padding: 1rem;
            background: var(--bg-color);
            border-radius: 6px;
            border-left: 3px solid var(--accent);
        }}
        .meta-label {{
            font-size: 0.875rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }}
        .meta-value {{
            font-size: 1.125rem;
            font-weight: 600;
            color: var(--text-primary);
        }}
        .score-badge {{
            display: inline-block;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            font-weight: 700;
            margin-top: 1rem;
        }}
        .score-badge.very-high {{
            background: #14532d;
            color: #4ade80;
        }}
        .score-badge.high {{
            background: #1e3a8a;
            color: #60a5fa;
        }}
        .score-badge.qualified {{
            background: #713f12;
            color: #fbbf24;
        }}
        .score-badge.disqualified {{
            background: #450a0a;
            color: #f87171;
        }}
        .section {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 2rem;
            margin-bottom: 2rem;
        }}
        .section-title {{
            font-size: 1.5rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .contacts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1rem;
        }}
        .contact-card {{
            background: var(--bg-color);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 1rem;
        }}
        .contact-name {{
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 0.25rem;
        }}
        .contact-title {{
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
        }}
        .contact-email {{
            font-size: 0.875rem;
            color: var(--accent);
            word-break: break-all;
        }}
        .dm-badge {{
            display: inline-block;
            background: var(--success);
            color: var(--bg-color);
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-top: 0.5rem;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }}
        th {{
            background: var(--bg-color);
            color: var(--text-secondary);
            text-align: left;
            padding: 0.75rem;
            border-bottom: 2px solid var(--border);
            font-size: 0.875rem;
            text-transform: uppercase;
            font-weight: 600;
        }}
        td {{
            padding: 0.75rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.875rem;
        }}
        tr:hover {{
            background: rgba(56, 189, 248, 0.05);
        }}
        .score-cell {{
            font-weight: 600;
            border-radius: 4px;
            padding: 0.5rem;
            text-align: center;
            min-width: 50px;
        }}
        .score-0 {{ background: rgba(239, 68, 68, 0.2); color: #fca5a5; }}
        .score-1 {{ background: rgba(249, 115, 22, 0.2); color: #fdba74; }}
        .score-2 {{ background: rgba(234, 179, 8, 0.2); color: #fcd34d; }}
        .score-3 {{ background: rgba(34, 197, 94, 0.2); color: #86efac; }}
        .grid-3 {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1rem;
            margin-top: 1rem;
        }}
        .brief-card {{
            background: var(--bg-color);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 1.5rem;
        }}
        .brief-card-title {{
            font-weight: 700;
            color: var(--accent);
            margin-bottom: 0.75rem;
            font-size: 1rem;
        }}
        .brief-card-content {{
            color: var(--text-secondary);
            font-size: 0.925rem;
            line-height: 1.6;
        }}
        .footer {{
            text-align: center;
            color: var(--text-secondary);
            font-size: 0.875rem;
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header Section -->
        <div class="header">
            <div class="header-title">{company_name}</div>
            <div class="header-meta">
                <div class="meta-item">
                    <div class="meta-label">Decision Maker</div>
                    <div class="meta-value">{dm_contact}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">SDR</div>
                    <div class="meta-value">{sdr_name}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Employees</div>
                    <div class="meta-value">{employees}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Location</div>
                    <div class="meta-value">{location}</div>
                </div>
            </div>
            <div style="border-top: 1px solid var(--border); padding-top: 1rem;">
                <div class="meta-label">Qualification Score</div>
                <div class="score-badge {tier_class}">{weighted_score}/10 - {qualification_tier}</div>
            </div>
        </div>

        <!-- Contacts Section -->
        <div class="section">
            <div class="section-title">👥 Contacts at {company_name}</div>
            <div class="contacts-grid">
                {contacts_html}
            </div>
        </div>

        <!-- Connected Calls Timeline -->
        <div class="section">
            <div class="section-title">📞 Connected Calls</div>
            <table>
                <thead>
                    <tr>
                        <th>Call Date</th>
                        <th>Disposition</th>
                        <th>Recording</th>
                        <th>Analysis Status</th>
                    </tr>
                </thead>
                <tbody>
                    {calls_timeline_html}
                </tbody>
            </table>
        </div>

        <!-- Per-Call BANTIC Matrix -->
        <div class="section">
            <div class="section-title">📊 Per-Call BANTIC Scores</div>
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

        <!-- Consolidated BANTIC Profile -->
        <div class="section">
            <div class="section-title">🎯 Consolidated BANTIC Profile (Best Scores)</div>
            <table>
                <thead>
                    <tr>
                        <th>Dimension</th>
                        <th>Best Score</th>
                        <th>Best Evidence</th>
                        <th>What's Missing</th>
                    </tr>
                </thead>
                <tbody>
                    {consolidated_rows}
                </tbody>
            </table>
        </div>

        <!-- AE Brief Sections -->
        <div class="section">
            <div class="section-title">📝 AE Handoff Brief</div>
            <div class="grid-3">
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
            </div>
            <div class="grid-3" style="margin-top: 1rem;">
                <div class="brief-card">
                    <div class="brief-card-title">Pain / Need</div>
                    <div class="brief-card-content">{pain_need}</div>
                </div>
                <div class="brief-card" style="grid-column: span 2;">
                    <div class="brief-card-title">Recommended Next Steps</div>
                    <div class="brief-card-content">{next_steps}</div>
                </div>
            </div>
        </div>

        <div class="footer">
            Generated by AE Handoff Brief Agent
        </div>
    </div>
</body>
</html>
"""


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
        if journey.calls:
            for call in journey.calls:
                call_date = call.get("call_date", "N/A")
                disposition = call.get("call_disposition_label", "N/A")
                recording = "✓" if call.get("recording_url") else "✗"
                status = call.get("analysis_status", "pending")
                calls_timeline_html += f'''
                <tr>
                    <td>{call_date}</td>
                    <td>{disposition}</td>
                    <td style="text-align: center;">{recording}</td>
                    <td>{status}</td>
                </tr>
                '''

        # Build per-call matrix HTML
        per_call_matrix_html = ""
        per_call_matrix = score_result.get("per_call_matrix", [])
        for call_data in per_call_matrix:
            scores = call_data.get("scores", {})
            weighted = call_data.get("weighted", 0)
            call_date = call_data.get("date", "N/A")

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

        # Determine tier CSS class
        tier = score_result.get("qualification_tier", "Disqualified")
        tier_class = tier.lower().replace(" ", "-")

        # Format template
        html = HTML_TEMPLATE.format(
            company_name=journey.company.name,
            dm_contact=journey.dm_contact.name if journey.dm_contact else "UNKNOWN",
            sdr_name=journey.sdr_name or "Unknown",
            employees=journey.company.employees or "UNKNOWN",
            location=journey.company.location or "UNKNOWN",
            weighted_score=score_result.get("weighted_score", 0),
            qualification_tier=tier,
            tier_class=tier_class,
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
