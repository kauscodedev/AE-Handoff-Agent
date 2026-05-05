# AE Handoff Brief Agent

Agentic handoff system that reconciles HubSpot for new "C - Meeting Scheduled" calls, claims durable work in Supabase, delegates specialist sub-agents for context gathering/transcription/analysis/judging/briefing, and generates Markdown handoff briefs plus HTML dashboards for Account Executives.

## Architecture

```
HubSpot API
   ↓
CoordinatorAgent
   ├─ TriggerDiscoveryAgent: rolling HubSpot reconciliation, paginated search
   ├─ RunLedgerAgent: durable claim/idempotency in ae_handoff_runs
   └─ HandoffPipelineAgent
        ├─ ContextFetchAgent: company/contact/call enrichment from HubSpot
        ├─ TranscriptionAgent: Deepgram Nova-3
        ├─ TranscriptAgent: OpenAI speaker cleanup
        ├─ TranscriptJudgeAgent: GLM-4.7 label review, non-critical
        ├─ DMDiscoveryAgent: decision-maker identification
        ├─ BANTICAnalysisAgent: OpenAI scoring
        ├─ FinalJudgeAgent: GLM-4.7 score review, non-critical
        ├─ ScoreAgent: deterministic weighted score
        └─ BriefAgent: Markdown, dashboard, HubSpot company update

Primary ledger: ae_handoff_runs
Per-call audit: ae_handoff_run_calls
Compatibility cache: calls
```

## Setup

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys:
# HUBSPOT_TOKEN=<your-token>
# SUPABASE_URL=<your-url>
# SUPABASE_SERVICE_KEY=<your-key>
# DEEPGRAM_API_KEY=<your-key>
# OPENAI_API_KEY=<your-key>
# NVIDIA_API_KEY=<your-key>

# Create logs directory
mkdir -p logs
```

## Usage

### Continuous Loop (Recommended)
```bash
python3 orchestrator.py                    # polls every 60 seconds
python3 orchestrator.py --interval 120     # custom interval (seconds)
```

### Single Run
```bash
python3 orchestrator.py --once             # one iteration only
```

## Output

Each generated brief is saved to `handoffs/<Company>_handoff.md` with sections:

- **Account Header**: Company name, DM contact, meeting time, SDR, BANTIC score
- **ICP Fit**: Company size, location, decision-maker verification
- **Current Process**: Current tools and workflows
- **Evaluating Tools**: Active evaluation timeline (if any)
- **Pain / Need**: Articulated problems from BANTIC analysis
- **Recommended Next Steps**: AE action items based on BANTIC gaps

Example:

```markdown
**ACCOUNT**: Garden State Honda
**DM CONTACT**: Mike Johnson
**MEETING SCHEDULED**: 2026-04-28T10:00:00
**SDR**: Sarah Chen
**BANTIC SCORE**: 7.2/10 (Qualified)

---

### ICP Fit
Garden State Honda is a 45-person automotive dealership in New Jersey...

### Current Process
They use a manual photo process with an external contractor...

### Evaluating Tools
No active evaluation timeline mentioned. Unknown if they've considered alternatives.

### Pain / Need
Mike mentioned "photos are taking too long" and "our process is slow."

### Recommended Next Steps
Ask about budget allocation for photo improvement. Clarify who approves the solution.
```

## Current Process

1. `CoordinatorAgent` runs during operating hours and asks `TriggerDiscoveryAgent` to reconcile HubSpot over a rolling lookback window.
2. `TriggerDiscoveryAgent` uses paginated HubSpot search for `C - Meeting Scheduled` calls and asks `RunLedgerAgent` which trigger IDs are already completed.
3. If the trigger call has a company association, Stage 2 fetches:
   - company details
   - all associated HubSpot contacts
   - all associated HubSpot calls, including HubSpot/Nooks Call Notes when present
4. Stage 2 narrows the analysis call set to:
   - `C - Meeting Scheduled`
   - `C - Callback High Intent`
   - `C - Callback Low Intent`
   - `C - Gave a Referral`
   - `Connected`
5. If the trigger call has no associated company, the pipeline falls back to an `INDIVIDUAL` trigger-call-only run instead of skipping it.
6. Deepgram transcribes recordings, OpenAI cleans speaker labels, OpenAI scores BANTIC with Call Notes as high-priority context when available, NVIDIA judges labels and BANTIC, Python computes the weighted score, and OpenAI writes the final handoff brief.
7. Supabase stores the trigger lifecycle in `ae_handoff_runs` and per-call processing state in `ae_handoff_run_calls`.
8. For company-backed runs, the final brief is written back to the HubSpot company property. For `INDIVIDUAL` runs, that HubSpot company update is skipped.

## Key Features

- **Quality Gate**: Only generates briefs when BANTIC analysis exists (no hallucinated content)
- **Evidence-Based**: Claims use transcript evidence plus HubSpot/Nooks Call Notes when available
- **No LLM Hallucination in Scoring**: Uses Python to calculate weighted scores
- **Multi-Call Intelligence**: Finds best evidence across all company calls
- **Ledger-Based Idempotency**: `ae_handoff_runs.trigger_call_id` + `status` is the source of truth for whether a trigger is done
- **Rolling Reconciliation**: HubSpot trigger discovery scans a lookback window and paginates results, so late-arriving records do not disappear behind a cursor
- **No-Company Fallback**: Trigger calls without a company can still generate an `INDIVIDUAL` handoff
- **Run Tracking**: Stores run-level and call-level pipeline state in `ae_handoff_runs` and `ae_handoff_run_calls`
- **Call Notes Aware**: Stores fetched Call Notes inside `ae_handoff_run_calls.bantic_scores.call_notes` and uses them during BANTIC analysis/judging
- **Standalone**: Separate from call-scoring-agent; uses same API keys

## File Structure

```
ae-handoff-brief-agent/
├── orchestrator.py              ← main loop: 9-stage pipeline
├── agents/
│   ├── coordinator.py           ← top-level agent loop
│   ├── discovery_agent.py       ← HubSpot trigger reconciliation
│   ├── ledger_agent.py          ← durable run claiming/idempotency
│   ├── pipeline_agent.py        ← delegates specialist stage chain
│   └── contracts.py             ← shared agent result/trigger contracts
├── stages/
│   ├── watcher.py              ← Stage 1: incremental HubSpot watcher
│   ├── fetch_agent.py          ← Stage 2: HubSpot company/contact/call fetch
│   ├── transcription.py        ← Stage 3: Deepgram submission
│   ├── clean_transcript.py     ← Stage 4: speaker labeling
│   ├── transcript_judge.py     ← Stage 4.1: speaker-label judge
│   ├── dm_discovery.py         ← Stage 4.5: decision-maker discovery
│   ├── bantic_analysis.py      ← Stage 5: BANTIC scoring
│   ├── final_judge.py          ← Stage 5.5: BANTIC score judge
│   ├── score_module.py         ← Stage 6: weighted score calc
│   └── ae_brief_agent.py       ← Stage 7: brief generation
├── lib/
│   ├── types.py                ← data structures
│   ├── supabase_client.py      ← Supabase queries
│   └── hubspot_client.py       ← HubSpot API helpers
├── handoffs/                    ← output folder for briefs
├── logs/                        ← orchestrator.log
├── .env.example
├── requirements.txt
└── README.md
```

## Database Schema

Requires these columns in `calls` table (from call-scoring-agent):
- `ae_brief_sent` (boolean) — marks when brief has been generated
- `ae_brief_generated_at` (timestamp) — when brief was created
- `analysis_status` should accept `completed`
- All BANTIC evidence columns (budget_evidence, authority_evidence, etc.)

The pipeline also expects:
- `ae_handoff_runs` — one row per trigger-call handoff run
- `ae_handoff_run_calls` — one row per in-scope analyzed call inside that run

HubSpot is the runtime source of truth for company and contact fetches. Supabase `ae_handoff_runs` is the durable processing ledger. The legacy `calls` table is kept as a compatibility cache for transcript reuse, analysis artifacts, and `ae_brief_sent` markers; it should not be the source of truth for trigger idempotency.

## Monitoring

Check `logs/orchestrator.log` for execution traces:

```bash
tail -f logs/orchestrator.log
```

Look for:
- `Coordinator tick`
- `Discovery reconciled X HubSpot Meeting Scheduled calls over 48h; Y need work`
- `Ledger claimed trigger <id> as run <id>`
- `✓ Stage 2 complete: <company> with X connected calls tracked`
- `✓ Stage 4.1 complete: X approved, Y revised`
- `✓ Stage 5: BANTIC analysis for 5 calls`
- `✓ Stage 5.5 complete: X approved, Y revised`
- `✓ Stage 6 complete: Overall Score X.X (Qualification Tier)`
- `✓ Brief saved: handoffs/Company_handoff.md`

## Notes

- **Deepgram is synchronous**: Nova-3 returns results immediately in the POST response
- **OpenAI cost**: ~$0.002-0.005 per call for all stages combined
- **Timestamps**: HubSpot `hs_timestamp` is milliseconds; code divides by 1000
- **API reuse**: Uses same credentials as call-scoring-agent (no new accounts needed)
- **Stage 1 source of truth**: HubSpot is searched directly; `ae_handoff_runs` is used for idempotency and run lifecycle
- **Stage 2 call filter**: only `Meeting Scheduled`, `Callback High Intent`, `Callback Low Intent`, `Gave a Referral`, and `Connected` calls are included for transcription/analysis
- **Watcher state**: the active agentic runtime does not depend on `.watcher_state.json`; it reconciles a rolling HubSpot lookback against `ae_handoff_runs`
- **NVIDIA judge calls**: Stage 4.1 and Stage 5.5 use 90-second request timeouts and continue on judge errors where possible

## Troubleshooting

### "No pending calls found"
- Check that calls in HubSpot have `hs_call_disposition` = "C - Meeting Scheduled"
- Verify `ae_handoff_runs.status` is not already `completed` for those trigger call IDs
- If a HubSpot call arrived late, increase the discovery lookback window in `agents/discovery_agent.py`
- Check HubSpot API token is valid

### "Fetch failed"
- Ensure the trigger call exists in HubSpot
- If the trigger has no company, verify the `INDIVIDUAL` fallback path is being used
- Check HUBSPOT_TOKEN is set correctly

### "Deepgram error"
- Verify DEEPGRAM_API_KEY is correct
- Ensure recording_url is a valid, publicly accessible URL

### "OpenAI error"
- Check OPENAI_API_KEY is set
- Verify you have sufficient API credits

## Author

Kaustubh Chauhan (kaustubh.chauhan@spyne.ai) — Agents & Automations, Spyne.ai
