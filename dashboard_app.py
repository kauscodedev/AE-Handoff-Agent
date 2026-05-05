#!/usr/bin/env python3
"""
AE Handoff Brief Agent — Dev Dashboard
Monitors orchestrator progress and call processing in real-time
"""

import os
import re
import json
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify
from dotenv import load_dotenv
from lib.supabase_client import get_supabase

load_dotenv()

app = Flask(__name__)

# Stage names and order
STAGES = {
    1: "Watcher",
    2: "Fetch Agent",
    3: "Transcription",
    4: "Clean Transcript",
    4.1: "Transcript Judge",
    4.5: "DM Discovery",
    5: "BANTIC Analysis",
    5.5: "Final Judge",
    6: "Score Module",
    7: "AE Brief Agent"
}

def get_orchestrator_status():
    """Check if orchestrator is running"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "orchestrator.py"],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            pid = result.stdout.strip().split('\n')[0]
            return {"running": True, "pid": pid}
        return {"running": False, "pid": None}
    except Exception as e:
        return {"running": False, "pid": None, "error": str(e)}

def parse_orchestrator_logs():
    """Parse orchestrator logs to extract current state"""
    log_file = Path("/Users/kaustubhchauhan/ae-handoff-brief-agent/logs/orchestrator.log")

    if not log_file.exists():
        return {
            "current_stage": None,
            "current_company": None,
            "current_call": None,
            "companies_processed": []
        }

    with open(log_file, 'r') as f:
        lines = f.readlines()

    # Get recent 500 lines for performance
    recent_lines = lines[-500:]
    text = ''.join(recent_lines)

    # Extract current processing info
    current_company = None
    current_stage = None
    current_call = None
    companies_processed = []

    # Find current company
    company_match = re.search(r'Processing company: (\d+) \(trigger call: (\d+)\)', text)
    if company_match:
        current_company = company_match.group(1)
        current_call = company_match.group(2)

    # Find current stage
    stage_matches = re.findall(r'→ Stage ([0-9.]+): (.*?)(?:\n|$)', text)
    if stage_matches:
        last_stage_num = float(stage_matches[-1][0])
        current_stage = {
            "number": last_stage_num,
            "name": STAGES.get(last_stage_num, stage_matches[-1][1])
        }

    # Extract completed companies
    complete_matches = re.findall(r'✓ Complete: (.*?)(?:\n|$)', text)
    companies_processed = list(set(complete_matches))

    return {
        "current_stage": current_stage,
        "current_company": current_company,
        "current_call": current_call,
        "companies_processed": companies_processed,
        "last_update": datetime.now().isoformat()
    }

def get_call_statistics():
    """Get call statistics from Supabase"""
    try:
        supabase = get_supabase()

        # Get total calls and briefed calls
        response = supabase.table("calls").select("ae_brief_sent").execute()
        calls = response.data

        total_calls = len(calls)
        briefed_calls = len([c for c in calls if c.get("ae_brief_sent")])
        pending_calls = total_calls - briefed_calls

        # Get calls with analysis
        analyzed_calls = len([c for c in calls if c.get("analysis_status") == "completed"])

        return {
            "total_calls": total_calls,
            "briefed_calls": briefed_calls,
            "pending_calls": pending_calls,
            "analyzed_calls": analyzed_calls
        }
    except Exception as e:
        return {
            "total_calls": 0,
            "briefed_calls": 0,
            "pending_calls": 0,
            "analyzed_calls": 0,
            "error": str(e)
        }

@app.route('/')
def index():
    """Serve dashboard HTML"""
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    """Get current system status"""
    orchestrator = get_orchestrator_status()
    logs = parse_orchestrator_logs()
    stats = get_call_statistics()

    return jsonify({
        "orchestrator": orchestrator,
        "logs": logs,
        "statistics": stats,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/logs/tail')
def api_logs_tail():
    """Get last N lines of orchestrator log"""
    log_file = Path("/Users/kaustubhchauhan/ae-handoff-brief-agent/logs/orchestrator.log")

    if not log_file.exists():
        return jsonify({"lines": []})

    with open(log_file, 'r') as f:
        lines = f.readlines()

    # Return last 50 lines
    recent_lines = lines[-50:]

    return jsonify({
        "lines": recent_lines,
        "total_lines": len(lines)
    })

if __name__ == '__main__':
    print("Starting AE Handoff Brief Agent Dashboard...")
    print("Access at: http://localhost:5000")
    app.run(debug=True, port=8000, use_reloader=False)
