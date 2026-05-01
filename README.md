# AE Handoff Brief Agent

Standalone 7-stage multi-agent pipeline that watches HubSpot for "C - Meeting Scheduled" calls, transcribes and analyzes them through the full BANTIC framework, and generates data-driven handoff briefs for Account Executives.

## Architecture

```
HubSpot API
   ↓ (searches HubSpot for C - Meeting Scheduled call activities)
Stage 1: HubSpot Watcher
   ↓ (fetches company + contacts + all associated calls)
Stage 2: Fetch Agent
   ↓ (submits recording to Deepgram Nova-3)
Stage 3: Transcription Agent
   ↓ (labels speakers with OpenAI gpt-4o-mini)
Stage 4: Clean Transcript Agent
   ↓ (scores on 6 BANTIC dimensions with OpenAI gpt-4o-mini)
Stage 5: BANTIC Analysis Agent
   ↓ (calculates weighted score with Python, no LLM)
Stage 6: Score Module
   ↓ (generates formatted brief with OpenAI gpt-4o)
Stage 7: AE Brief Agent
   ↓
Markdown brief saved to handoffs/<Company>_handoff.md
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

## Key Features

- **Quality Gate**: Only generates briefs when BANTIC analysis exists (no hallucinated content)
- **Evidence-Based**: Every claim cites verbatim transcript quotes
- **No LLM Hallucination in Scoring**: Uses Python to calculate weighted scores
- **Multi-Call Intelligence**: Finds best evidence across all company calls
- **Standalone**: Separate from call-scoring-agent; uses same API keys

## File Structure

```
ae-handoff-brief-agent/
├── orchestrator.py              ← main loop: 7-stage pipeline
├── stages/
│   ├── watcher.py              ← Stage 1: searches HubSpot for Meeting Scheduled calls
│   ├── fetch_agent.py          ← Stage 2: company + contacts + calls
│   ├── transcription.py        ← Stage 3: Deepgram submission
│   ├── clean_transcript.py     ← Stage 4: speaker labeling
│   ├── bantic_analysis.py      ← Stage 5: BANTIC scoring
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
- All BANTIC evidence columns (budget_evidence, authority_evidence, etc.)

## Monitoring

Check `logs/orchestrator.log` for execution traces:

```bash
tail -f logs/orchestrator.log
```

Look for:
- `✓ Stage 1: Watcher found X pending calls`
- `✓ Stage 2: Fetch complete: X contacts, Y calls`
- `✓ Stage 5: BANTIC analysis for 5 calls`
- `✓ Stage 6 complete: Overall Score X.X (Qualification Tier)`
- `✓ Brief saved: handoffs/Company_handoff.md`

## Notes

- **Deepgram is synchronous**: Nova-3 returns results immediately in the POST response
- **OpenAI cost**: ~$0.002-0.005 per call for all stages combined
- **Timestamps**: HubSpot `hs_timestamp` is milliseconds; code divides by 1000
- **API reuse**: Uses same credentials as call-scoring-agent (no new accounts needed)

## Troubleshooting

### "No pending calls found"
- Check that calls in HubSpot have `hs_call_disposition` = "C - Meeting Scheduled"
- Verify the call has an associated company in HubSpot
- Verify `ae_brief_sent` is not already True for those call IDs in Supabase
- Check HubSpot API token is valid

### "Fetch failed"
- Ensure call has associated company_id in HubSpot
- Check HUBSPOT_TOKEN is set correctly

### "Deepgram error"
- Verify DEEPGRAM_API_KEY is correct
- Ensure recording_url is a valid, publicly accessible URL

### "OpenAI error"
- Check OPENAI_API_KEY is set
- Verify you have sufficient API credits

## Author

Kaustubh Chauhan (kaustubh.chauhan@spyne.ai) — Agents & Automations, Spyne.ai
