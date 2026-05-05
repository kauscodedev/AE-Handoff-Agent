# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python 3 agentic handoff system that automatically generates Account Executive handoff briefs after sales calls. When a call is marked "C - Meeting Scheduled" in HubSpot, a CoordinatorAgent reconciles HubSpot against a durable Supabase run ledger, claims pending trigger work, delegates specialist sub-agents for context/transcription/analysis/judging/briefing, and produces a Markdown brief + HTML dashboard for the AE taking over the deal.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in all 6 keys
```

Required env vars (see `.env.example`): `HUBSPOT_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DEEPGRAM_API_KEY`, `OPENAI_API_KEY`, `NVIDIA_API_KEY`.

## Running

```bash
# Continuous polling loop (default 60s interval)
python3 orchestrator.py

# Custom interval
python3 orchestrator.py --interval 120

# One-shot run (useful for testing)
python3 orchestrator.py --once

# Run judge smoke tests (no pytest needed — standalone scripts)
python3 test_judge.py
python3 test_transcript_judge.py

# Dev monitoring dashboard (Flask, port 8000; requires 'flask' package)
pip install flask
python3 dashboard_app.py
```

Development utilities (not part of the pipeline):

**Root-level scripts:**
- `check_pending.py` — queries Supabase `calls` table for `ae_brief_sent = False` rows; prints backlog count + first 6 call IDs
- `test_hubspot_brief.py` — manually fires `update_company_property()` against a hardcoded company ID (HubSpot write-back integration test)
- `verify_hubspot_brief.py` — reads `ae_handoff_brief` property from HubSpot for the same hardcoded company; confirms brief was persisted
- `dashboard_app.py` — Flask dev dashboard monitoring orchestrator progress; parses `orchestrator.log` and queries Supabase; serves at http://localhost:8000. Note: `flask` is not in `requirements.txt`; install separately with `pip install flask`.

**Scratch utilities:**
- `scratch/test_supabase.py` — verify Supabase connectivity
- `scratch/debug_fetch.py` — inspect Stage 2 fetch output
- `scratch/reset_flags.py` — reset `ae_brief_sent = False` to re-process rows
- `scratch/test_operating_hours.py` — verify IST operating window logic (17:00–04:00 IST)

## Agentic Runtime Architecture

The live runtime is coordinated through `agents/`, not the old local watcher cursor. The specialist stage modules in `stages/` still do the actual domain work, but they are now delegated behind a durable coordinator/ledger spine.

| Agent | File | What it owns |
|---|---|---|
| CoordinatorAgent | `agents/coordinator.py` | Top-level loop; asks discovery for work, claims triggers, delegates execution, records final state |
| TriggerDiscoveryAgent | `agents/discovery_agent.py` | Reconciles HubSpot `C - Meeting Scheduled` calls via 48-hour rolling lookback window (limit=500); filters by ledger `should_process()` |
| RunLedgerAgent | `agents/ledger_agent.py` | Durable idempotency and claiming via `ae_handoff_runs.trigger_call_id + status` |
| HandoffPipelineAgent | `agents/pipeline_agent.py` | Executes the specialist stage chain for one claimed trigger |
| Contracts | `agents/contracts.py` | Shared frozen dataclasses: `TriggerCandidate` (HubSpot trigger record), `AgentResult` (agent response envelope) |

Specialist stages execute sequentially per trigger; Stage 5 (BANTIC scoring) runs calls in parallel via `ThreadPoolExecutor`.

| Stage | File | What it does |
|---|---|---|
| 2 | `stages/fetch_agent.py` | Fetches company/contact/call data from HubSpot, including Call Notes (`hs_call_body` / `hs_body_preview`) when present; narrows analysis calls to `C - Meeting Scheduled`, `C - Callback High Intent`, `C - Callback Low Intent`, `C - Gave a Referral`, and `Connected`; merges in stored transcript/analysis state from Supabase |
| 3 | `stages/transcription.py` | Submits recording URL to Deepgram Nova-3 (synchronous STT + diarization via REST API) |
| 4 | `stages/clean_transcript.py` | gpt-4o-mini relabels Speaker 0/1 → `[SDR]`/`[PROSPECT]`/`[VOICEMAIL/IVR]`/`[RECEPTIONIST]` |
| 4.1 | `stages/transcript_judge.py` | GLM-4.7 with thinking verifies speaker labels are correct; catches global swaps ([SDR]↔[PROSPECT]) and individual turn mismatches; logs verdict + corrections to `logs/transcript_judge_feedback.jsonl` |
| 4.5 | `stages/dm_discovery.py` | gpt-4o-mini analyzes cleaned transcripts to identify the actual decision-maker; fuzzy substring-matches back to contacts list; falls back to `contacts[0]` |
| 5 | `stages/bantic_analysis.py` | gpt-4o-mini scores 6 BANTIC dimensions per call in parallel (0–3 each) via `ThreadPoolExecutor(max_workers=10)`; HubSpot/Nooks Call Notes are high-priority context when present |
| 5.5 | `stages/final_judge.py` | GLM-4.7 with thinking reviews BANTIC scores for accuracy using transcript + Call Notes; revises only clearly wrong scores; logs verdict + changes to `logs/judge_feedback.jsonl` |
| 6 | `stages/score_module.py` | Pure Python weighted score — no LLM (avoids hallucination in math) |
| 7 | `stages/ae_brief_agent.py` | gpt-4o writes Markdown brief; `lib/html_generator.py` builds HTML dashboard |

Shared infrastructure lives in `lib/`: `types.py` (plain Python classes), `supabase_client.py`, `hubspot_client.py`, `html_generator.py`.

## Key Behaviours to Know

- **Operating hours gate**: orchestrator only runs `coordinator.run_once()` during **17:00–04:00 IST**; outside that window it polls every 60 seconds (no agent work, just rechecking time). Use `--once` to bypass for testing.
- **Primary idempotency**: `ae_handoff_runs.trigger_call_id + status` is the source of truth. Completed runs are skipped even if legacy `calls` rows are missing or stale.
- **Compatibility marker**: `calls.ae_brief_sent` is still written for old tooling and transcript/cache reuse, but it must not be treated as the primary trigger ledger.
- **`journey.calls` are raw dicts**: `CompanyJourney.calls` is a list of plain dicts (from HubSpot/Supabase), not `Call` objects. The orchestrator builds `Call` objects from them before Stages 3–7.
- **Transcript reuse**: if `raw_transcript` already exists in the Supabase row, Stage 3 is skipped.
- **Best score wins**: Stage 6 takes the highest per-dimension score across all calls for a company, not the average.
- **Score formula** (Stage 6, `score_module.py`): `(B×5 + A×20 + N×25 + T×15 + I×15 + CP×20) / 30`. Tier mapping: ≥8.1 = "Very High Intent", 8.0 = "High Intent", 5.0–7.9 = "Qualified", <5.0 = "Disqualified".
- **Models**: Stages 4, 4.5, and 5 use `gpt-4o-mini` (temperature=0); Stages 4.1 and 5.5 use GLM-4.7 via NVIDIA API (temperature=0); Stage 7 uses `gpt-4o` (temperature=0).
- **PID lockfile**: orchestrator writes `/tmp/ae_handoff_orchestrator.lock` on startup to prevent duplicate instances.
- **Trigger discovery**: `TriggerDiscoveryAgent` scans a rolling HubSpot lookback window and paginates search results, then reconciles candidates against `ae_handoff_runs`.
- **Run status lifecycle**: `ae_handoff_runs.status` flows as `discovered → processing → completed` or `failed`. Failed runs are automatically retried on the next coordinator tick.
- **Local watcher state is legacy**: `.watcher_state.json` and `stages/watcher.py` are compatibility leftovers. The active agentic runtime should not depend on them for correctness.
- **Allowed analysis call set**: Stage 2 only includes `Meeting Scheduled`, `Callback High Intent`, `Callback Low Intent`, `Gave a Referral`, and `Connected` calls, and only up to the trigger call date.
- **Call Notes**: Stage 2 fetches HubSpot Call Notes for trigger and history calls. Stage 5 treats notes as high-priority BANTIC context; Stage 5.5 sees the same notes so the judge does not undo notes-based scoring. Notes are persisted in `ae_handoff_run_calls.bantic_scores.call_notes` because there is no dedicated call-notes column.
- **No-company trigger fallback**: if a trigger has no company association, the pipeline creates an `INDIVIDUAL` trigger-call-only journey instead of skipping it.
- **DM confidence gating**: Stage 4.5 only updates `dm_contact` if confidence is `"high"` or `"medium"`; low-confidence results fall back to `contacts[0]`.
- **HubSpot is the CRM source of truth**: company details, contacts, and associated calls come from HubSpot.
- **Supabase run tables are the processing source of truth**: `ae_handoff_runs` and `ae_handoff_run_calls` own lifecycle/audit state. The legacy `calls` table is a cache/compatibility store for transcripts, analysis artifacts, and `ae_brief_sent`.
- **Companies table is not business source of truth**: it is only upserted because the legacy `calls` table has a foreign key on `hubspot_company_id`; it should not block trigger discovery or idempotency.
- **BANTIC analysis status**: Stage 5 writes `analysis_status = "completed"`; Supabase rejects `"complete"` via `calls_analysis_status_check`.
- **NVIDIA judge timeouts**: Stages 4.1 and 5.5 set 30-second request timeouts for NVIDIA GLM-4.7 calls; judge failures log as warnings and the pipeline continues (judges are non-critical — they only revise clearly wrong scores).
- **Run tracking**: the orchestrator writes `ae_handoff_runs` and `ae_handoff_run_calls` throughout the run so brief generation can be audited at trigger and call level.
- **Testing reality**: There is no formal automated test suite. `test_judge.py` and `test_transcript_judge.py` are judge smoke scripts, while `scratch/test_supabase.py` is a manual connectivity probe.
- **Transcript corrections** (Stage 4.1): Never rewrites dialogue — applies label-only corrections via deterministic string replacement using temp placeholders to avoid double-replacement during global SDR↔PROSPECT swaps. Verdicts logged to `logs/transcript_judge_feedback.jsonl`.
- **BANTIC judge model** (Stage 5.5): Uses GLM-4.7 via NVIDIA API (`integrate.api.nvidia.com`); requires `NVIDIA_API_KEY` env var
- **Non-overcritical judge**: Stage 5.5 only revises scores if clearly wrong (evidence doesn't support it, topic never discussed but scored >0, or off by 2+ points). Full feedback logged to `logs/judge_feedback.jsonl`.

## Outputs

- `handoffs/<Company>_handoff.md` — Markdown brief (5 sections: ICP Fit, Current Process, Evaluating Tools, Pain/Need, Next Steps). Note: Path is hardcoded to `/Users/kaustubhchauhan/ae-handoff-brief-agent/handoffs/` in `ae_brief_agent.py`.
- `dashboards/<Company>_dashboard.html` — Standalone warm-theme HTML dashboard (self-contained; auto-created relative to project root).
- HubSpot company property `ae_handoff_brief` — brief text written back to HubSpot via `update_company_property()` for non-INDIVIDUAL runs.
- `logs/orchestrator.log` — Structured log output.
- `logs/judge_feedback.jsonl` — Per-run BANTIC judge verdicts (original vs final scores, thinking snippet, reasons for revision).
- `logs/transcript_judge_feedback.jsonl` — Per-run transcript judge verdicts (corrections applied, thinking snippet).

See `ARCHITECTURE.md` for per-stage cost, error handling, and design rationale.
