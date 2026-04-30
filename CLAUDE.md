# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python 3 multi-agent pipeline that automatically generates Account Executive handoff briefs after sales calls. When a call is marked "C - Meeting Scheduled" in HubSpot, the pipeline transcribes the recording, scores it on 6 BANTIC dimensions, and produces a Markdown brief + HTML dashboard for the AE taking over the deal.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in all 5 keys
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
```

Scratch utilities (not part of the pipeline):
- `scratch/test_supabase.py` — verify Supabase connectivity
- `scratch/debug_fetch.py` — inspect Stage 2 fetch output
- `scratch/reset_flags.py` — reset `ae_brief_sent = False` to re-process rows

## Pipeline Architecture (9 Stages)

Each stage is a module in `stages/`. They execute sequentially per company; Stage 5 (BANTIC scoring) runs calls in parallel via `ThreadPoolExecutor`.

| Stage | File | What it does |
|---|---|---|
| 1 | `stages/watcher.py` | Queries Supabase for unprocessed "C - Meeting Scheduled" calls from the last 24h |
| 2 | `stages/fetch_agent.py` | Fetches company/contact/call data from HubSpot; filters for "C - " or "Connected" disposition calls only; upserts to Supabase |
| 3 | `stages/transcription.py` | Submits recording URL to Deepgram Nova-3 (synchronous STT + diarization via REST API) |
| 4 | `stages/clean_transcript.py` | gpt-4o-mini relabels Speaker 0/1 → `[SDR]`/`[PROSPECT]`/`[VOICEMAIL/IVR]`/`[RECEPTIONIST]` |
| 4.1 | `stages/transcript_judge.py` | GLM-4.7 with thinking verifies speaker labels are correct; catches global swaps ([SDR]↔[PROSPECT]) and individual turn mismatches; logs verdict + corrections to `logs/transcript_judge_feedback.jsonl` |
| 4.5 | `stages/dm_discovery.py` | gpt-4o-mini analyzes cleaned transcripts to identify the actual decision-maker; fuzzy substring-matches back to contacts list; falls back to `contacts[0]` |
| 5 | `stages/bantic_analysis.py` | gpt-4o-mini scores 6 BANTIC dimensions per call in parallel (0–3 each) via `ThreadPoolExecutor(max_workers=10)` |
| 5.5 | `stages/final_judge.py` | GLM-4.7 with thinking reviews BANTIC scores for accuracy; revises only clearly wrong scores; logs verdict + changes to `logs/judge_feedback.jsonl` |
| 6 | `stages/score_module.py` | Pure Python weighted score — no LLM (avoids hallucination in math) |
| 7 | `stages/ae_brief_agent.py` | gpt-4o writes Markdown brief; `lib/html_generator.py` builds HTML dashboard |

Shared infrastructure lives in `lib/`: `types.py` (plain Python classes), `supabase_client.py`, `hubspot_client.py`, `html_generator.py`.

## Key Behaviours to Know

- **Idempotent**: the `ae_brief_sent` flag in Supabase prevents re-processing. Use `scratch/reset_flags.py` to re-run.
- **Transcript reuse**: if `raw_transcript` already exists in the Supabase row, Stage 3 is skipped.
- **Best score wins**: Stage 6 takes the highest per-dimension score across all calls for a company, not the average.
- **Score formula** (Stage 6, `score_module.py`): `(B×5 + A×20 + N×25 + T×15 + I×15 + CP×20) / 30`. Tier mapping: ≥8.1 = "Very High Intent", 8.0 = "High Intent", 5.0–7.9 = "Qualified", <5.0 = "Disqualified".
- **Models**: Stages 4, 4.5, and 5 use `gpt-4o-mini` (temperature=0); Stages 4.1 and 5.5 use GLM-4.7 via NVIDIA API (temperature=0); Stage 7 uses `gpt-4o` (temperature=0).
- **PID lockfile**: orchestrator writes `/tmp/ae_handoff_orchestrator.lock` on startup to prevent duplicate instances.
- **Watcher time window**: Stage 1 only picks up calls with `call_date >= start of yesterday`; rows older than ~2 days are never processed even with `ae_brief_sent = False`.
- **DM confidence gating**: Stage 4.5 only updates `dm_contact` if confidence is `"high"` or `"medium"`; low-confidence results fall back to `contacts[0]`.
- **`upsert_contact` schema gap**: `supabase_client.upsert_contact()` strips the `is_dm` field before upserting because the Supabase schema may not have that column yet.
- **No tests**: There are no test files in the project. `scratch/test_supabase.py` is a manual connectivity probe only.
- **Transcript judge** (Stage 4.1): Uses GLM-4.7 via NVIDIA API to verify speaker labels ([SDR]/[PROSPECT]) are correct; catches global swaps and individual turn mismatches
- **Transcript corrections applied programmatically**: Stage 4.1 never rewrites dialogue content — only corrects labels via deterministic string replacement (prevents hallucination)
- **Transcript judge log**: verdict, corrections applied, thinking snippet appended to `logs/transcript_judge_feedback.jsonl` per call
- **BANTIC judge model** (Stage 5.5): Uses GLM-4.7 via NVIDIA API (`integrate.api.nvidia.com`); requires `NVIDIA_API_KEY` env var
- **Non-overcritical judge**: Stage 5.5 only revises scores if clearly wrong (evidence doesn't support it, topic never discussed but scored >0, or off by 2+ points)
- **BANTIC judge log**: full feedback (thinking, original vs final scores, change reasons) appended to `logs/judge_feedback.jsonl` per call run

## Outputs

- `handoffs/<Company>_handoff.md` — Markdown brief (5 sections: ICP Fit, Current Process, Evaluating Tools, Pain/Need, Next Steps). Note: Path is hardcoded to `/Users/kaustubhchauhan/ae-handoff-brief-agent/handoffs/` in `ae_brief_agent.py`.
- `dashboards/<Company>_dashboard.html` — Standalone dark-theme HTML dashboard (self-contained; auto-created relative to project root).
- `logs/orchestrator.log` — Structured log output.
