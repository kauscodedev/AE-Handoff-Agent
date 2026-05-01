# AE Handoff Brief Agent

Standalone 9-stage multi-agent pipeline that watches HubSpot for new "C - Meeting Scheduled" calls, fetches the full company or trigger-call context, transcribes and analyzes the relevant call set through the BANTIC framework, and generates Markdown handoff briefs plus HTML dashboards for Account Executives.

## Architecture

```
HubSpot API
   ↓ (searches HubSpot for C - Meeting Scheduled call activities)
Stage 1: HubSpot Watcher
   ↓ (fetches HubSpot company + contacts + relevant associated calls)
Stage 2: Fetch Agent
   ↓ (submits recording to Deepgram Nova-3)
Stage 3: Transcription Agent
   ↓ (labels speakers with OpenAI gpt-4o-mini)
Stage 4: Clean Transcript Agent
   ↓ (verifies speaker labels with GLM-4.7)
Stage 4.1: Transcript Judge
   ↓ (identifies the actual decision maker)
Stage 4.5: DM Discovery Agent
   ↓ (scores on 6 BANTIC dimensions with OpenAI gpt-4o-mini)
Stage 5: BANTIC Analysis Agent
   ↓ (reviews and corrects clearly wrong scores with GLM-4.7)
Stage 5.5: Final Judge
   ↓ (calculates weighted score with Python, no LLM)
Stage 6: Score Module
   ↓ (generates formatted brief with OpenAI gpt-4o)
Stage 7: AE Brief Agent
   ↓
Markdown brief saved to handoffs/<Company>_handoff.md
HTML dashboard saved to dashboards/<Company>_dashboard.html
Run + call state saved to ae_handoff_runs / ae_handoff_run_calls
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

1. `stages/watcher.py` polls HubSpot for new `C - Meeting Scheduled` calls since the last watcher timestamp in `.watcher_state.json`.
2. The watcher filters out trigger calls already marked `ae_brief_sent = True` in Supabase.
3. If the trigger call has a company association, Stage 2 fetches:
   - company details
   - all associated HubSpot contacts
   - all associated HubSpot calls
4. Stage 2 narrows the analysis call set to:
   - `C - Meeting Scheduled`
   - `C - Callback High Intent`
   - `C - Callback Low Intent`
   - `C - Gave a Referral`
   - `Connected`
5. If the trigger call has no associated company, the pipeline falls back to an `INDIVIDUAL` trigger-call-only run instead of skipping it.
6. Deepgram transcribes recordings, OpenAI cleans speaker labels, NVIDIA judges labels and BANTIC, Python computes the weighted score, and OpenAI writes the final handoff brief.
7. Supabase stores both the trigger-level run record and per-call processing state in `ae_handoff_runs` and `ae_handoff_run_calls`.
8. For company-backed runs, the final brief is written back to the HubSpot company property. For `INDIVIDUAL` runs, that HubSpot company update is skipped.

## Key Features

- **Quality Gate**: Only generates briefs when BANTIC analysis exists (no hallucinated content)
- **Evidence-Based**: Every claim cites verbatim transcript quotes
- **No LLM Hallucination in Scoring**: Uses Python to calculate weighted scores
- **Multi-Call Intelligence**: Finds best evidence across all company calls
- **Incremental Watcher**: Only fetches HubSpot Meeting Scheduled calls newer than the last watcher run
- **No-Company Fallback**: Trigger calls without a company can still generate an `INDIVIDUAL` handoff
- **Run Tracking**: Stores run-level and call-level pipeline state in `ae_handoff_runs` and `ae_handoff_run_calls`
- **Standalone**: Separate from call-scoring-agent; uses same API keys

## File Structure

```
ae-handoff-brief-agent/
├── orchestrator.py              ← main loop: 9-stage pipeline
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

HubSpot is the runtime source of truth for company and contact fetches. Supabase is used for persistence, transcript reuse, analysis state, idempotency, and run tracking.

## Monitoring

Check `logs/orchestrator.log` for execution traces:

```bash
tail -f logs/orchestrator.log
```

Look for:
- `✓ Watcher found X NEW Meeting Scheduled calls in HubSpot since last run`
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
- **Stage 1 source of truth**: HubSpot is searched directly; Supabase is used for the `ae_brief_sent` idempotency check and run/call persistence
- **Stage 2 call filter**: only `Meeting Scheduled`, `Callback High Intent`, `Callback Low Intent`, `Gave a Referral`, and `Connected` calls are included for transcription/analysis
- **Watcher state**: `.watcher_state.json` stores the last watcher timestamp in UTC milliseconds
- **NVIDIA judge calls**: Stage 4.1 and Stage 5.5 use 90-second request timeouts and continue on judge errors where possible

## Troubleshooting

### "No pending calls found"
- Check that calls in HubSpot have `hs_call_disposition` = "C - Meeting Scheduled"
- Verify `ae_brief_sent` is not already True for those call IDs in Supabase
- Check `.watcher_state.json` if you expect an older trigger call to be re-picked
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
