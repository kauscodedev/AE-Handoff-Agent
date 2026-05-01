# AE Handoff Brief Agent — Architecture Deep Dive

## Overview

The AE Handoff Brief Agent is a standalone 9-stage multi-agent pipeline that transforms raw HubSpot call data into evidence-based Account Executive handoff briefs and HTML dashboards. It operates independently from call-scoring-agent but uses the same Supabase database for call persistence, transcripts, BANTIC data, and idempotency flags.

## 9-Stage Pipeline

### Stage 1: HubSpot Watcher
**File**: `stages/watcher.py`

**Purpose**: Continuously searches HubSpot directly for new calls with the "C - Meeting Scheduled" disposition, then filters out calls already briefed in Supabase.

**Input**: 
- HubSpot API query: calls where `hs_call_disposition = "C - Meeting Scheduled"` and `hs_timestamp >= last watcher timestamp`
- Supabase idempotency check: skip call IDs where `ae_brief_sent = True`

**Output**:
- List of pending call objects: `[{hubspot_call_id, hubspot_company_id, call_date, activity_date, assigned_to, call_outcome, recording_url}, ...]`

**Frequency**: Every 60 seconds (configurable)

**Cost**: Free (HubSpot API)

**Important behavior**:
- The watcher stores its last successful UTC timestamp in `.watcher_state.json`.
- If no watcher state exists yet, the first search falls back to the beginning of yesterday.
- Calls without an associated HubSpot company are not skipped anymore; they are marked as `INDIVIDUAL` so Stage 2 can run a trigger-call-only fallback path.

---

### Stage 2: Fetch Agent
**File**: `stages/fetch_agent.py`

**Purpose**: Gathers complete company context from HubSpot and persists/merges the in-scope call state with Supabase.

**Input**: 
- `company_id` from Stage 1 trigger call, or `INDIVIDUAL` for no-company trigger fallback

**Fetches**:
- Company details: name, headcount, location
- All contacts at company: name, title, email
- All HubSpot calls associated with the company
- In-scope call details: activity date, owner, outcome, recording URL
- Existing call rows are merged from Supabase for transcript reuse and analysis-state continuity

**Output**:
- `CompanyJourney` object with:
  - `company`: Company details
  - `contacts`: List of Contact objects
  - `calls`: List of in-scope call dicts for the trigger run
  - `dm_contact`: Identified decision maker (if any)

**Cost**: ~$0.0005 (HubSpot API calls)

**Error Handling**:
- Returns None if company not found
- Returns empty journey if no eligible calls are found
- If `company_id == "INDIVIDUAL"`, builds a single-call fallback journey from the trigger call only

**Call filter**:
- `C - Meeting Scheduled`
- `C - Callback High Intent`
- `C - Callback Low Intent`
- `C - Gave a Referral`
- `Connected`

Only calls up to the trigger call date are included, so later activity does not leak into the handoff.

---

### Stage 3: Transcription Agent
**File**: `stages/transcription.py`

**Purpose**: Submits call recordings to Deepgram Nova-3 for STT and intelligence extraction.

**Input**: 
- Recording URL from call
- Call metadata

**Deepgram Features Enabled**:
- `diarize`: Speaker identification (Speaker 0, Speaker 1)
- `smart_format`: Punctuation, capitalization, formatting
- `detect_entities`: Companies, people, locations
- `sentiment`: Word-level sentiment analysis
- `topics`: Auto-detected key topics
- `intents`: Buying intent, urgency, etc.

**Output**:
- `raw_transcript`: Diarized transcript with speakers
- `deepgram_entities`: Extracted entities (JSON)
- `deepgram_sentiment`: Sentiment distribution
- `deepgram_topics`: Detected topics
- `transcription_status`: "completed"

**Cost**: $0.0043/minute (pre-recorded audio)

**Note**: Deepgram Nova-3 is **synchronous** — returns results in original POST response (<300ms). No polling needed.

---

### Stage 4: Clean Transcript Agent
**File**: `stages/clean_transcript.py`

**Purpose**: Uses OpenAI to identify and label speakers as [SDR], [PROSPECT], [VOICEMAIL/IVR], or [RECEPTIONIST].

**Input**:
- Raw transcript with Speaker 0/1
- Deepgram intelligence (entities, sentiment, topics)
- Company name
- SDR name (if known)

**Classification Logic**:
1. First detect voicemail/IVR/receptionist (monologues, automated phrases)
2. Identify SDR (introduces self, asks qualifying questions, pitches, drives call structure)
3. Identify prospect (answers phone, reacts to pitch, asks clarifying questions)
4. Handle edge cases (gatekeepers, silent prospects, question-asking prospects)

**Output**:
- `cleaned_transcript`: Transcript with each line prefixed with [ROLE]: <dialogue>

**Cost**: $0.00015 per call (gpt-4o-mini, ~50 tokens input/output)

**Model**: gpt-4o-mini with temperature=0 (deterministic)

---

### Stage 4.1: Transcript Judge
**File**: `stages/transcript_judge.py`

**Purpose**: Uses GLM-4.7 through NVIDIA's API to verify that Stage 4 speaker labels are correct.

**Input**:
- Raw Deepgram transcript
- Cleaned role-labeled transcript

**Checks**:
- Global SDR/prospect swaps
- Individual mislabeled turns
- Voicemail, IVR, and receptionist turns mislabeled as SDR/prospect

**Output**:
- Approved or corrected cleaned transcript
- Judge feedback appended to `logs/transcript_judge_feedback.jsonl`
- Corrected transcript persisted to Supabase when changes are made

**Model**: `z-ai/glm4.7` via `https://integrate.api.nvidia.com/v1`

**Timeout**: 30 seconds per request in the current code path

**Safety Principle**: Corrections are applied programmatically to labels only. Stage 4.1 never rewrites dialogue content.

---

### Stage 4.5: DM Discovery Agent
**File**: `stages/dm_discovery.py`

**Purpose**: Uses cleaned transcripts to identify the actual decision maker rather than assuming the first associated contact.

**Input**:
- `CompanyJourney`
- Cleaned transcript list
- HubSpot contact list

**Output**:
- Updates `journey.dm_contact` when confidence is `high` or `medium`
- Falls back to `contacts[0]` on low confidence or no match

**Matching Logic**:
- LLM extracts the likely decision-maker name/title from the conversation
- Code fuzzy substring-matches the result back to the HubSpot contacts list

**Model**: gpt-4o-mini with temperature=0

---

### Stage 5: BANTIC Analysis Agent
**File**: `stages/bantic_analysis.py`

**Purpose**: Scores the call on 6 B2B qualification dimensions and extracts evidence quotes.

**Framework**: BANTIC
- **B** — Budget: Does prospect have allocated budget?
- **A** — Authority: Is prospect a decision maker / influencer?
- **N** — Need: Does prospect have articulated pain?
- **T** — Timeline: How soon do they want to implement?
- **I** — Impact: What business impact would solution deliver?
- **C** — Current Process: What do they use today?

**Scoring Scale**: 0-3 per dimension
- 0 = Not discussed
- 1 = Discussed but vague / deflected
- 2 = Good — clear, substantive response
- 3 = Excellent — highly specific, concrete details

**Output** (BANTICScore object):
- `score_budget` through `score_current_process`: 0-3 each
- `budget_evidence` through `current_process_evidence`: Verbatim quotes
- `budget_info_captured` through `current_process_info_captured`: What was learned
- `overall_summary`: 3-4 sentence executive summary
- `sdr_coaching_note`: What to cover on next call

**Cost**: $0.0005 per call (gpt-4o-mini, ~200-300 tokens input/output)

**Model**: gpt-4o-mini with temperature=0

**Key Principle**: All scores based strictly on transcript evidence. No inference beyond what was said.

**Persistence**:
- Writes BANTIC fields back to Supabase.
- Sets `analysis_status = "completed"`; the database check constraint rejects `"complete"`.

---

### Stage 5.5: Final Judge
**File**: `stages/final_judge.py`

**Purpose**: Uses GLM-4.7 through NVIDIA's API to review BANTIC scores and revise only clearly wrong values.

**Input**:
- Cleaned transcript
- Original BANTIC scores, evidence, and captured info

**Output**:
- Approved or revised `BANTICScore`
- Judge feedback appended to `logs/judge_feedback.jsonl`
- Revised fields persisted to Supabase when changes are made

**Model**: `z-ai/glm4.7` via `https://integrate.api.nvidia.com/v1`

**Timeout**: 30 seconds per request in the current code path

**Principle**: Non-overcritical review. The judge should not nitpick borderline calls.

---

### Stage 6: Score Module (Python, No LLM)
**File**: `stages/score_module.py`

**Purpose**: Calculates company-wide weighted BANTIC score and qualification tier using Python.

**Input**:
- All BANTIC scores from all company calls

**Logic**:
1. For each dimension, find the **best (highest) score** across all calls
2. Get corresponding evidence quote for that best score
3. Calculate weighted score:
   ```
   weighted = (Budget×5 + Authority×20 + Need×25 + Timeline×15 + Impact×15 + CurrentProcess×20) / 30
   ```
4. Map to tier:
   - 8.1-10.0 = "Very High Intent"
   - 8.0 = "High Intent"
   - 5.0-7.9 = "Qualified"
   - 0-4.9 = "Disqualified"

**Output**:
- `weighted_score`: 0-10 (e.g., 7.2)
- `qualification_tier`: String (e.g., "Qualified")
- `best_scores`: Dict with best score + evidence per dimension
- `dimensions_table`: Markdown table for brief

**Cost**: $0 (Python only)

**Design Principle**: Avoids LLM hallucination in math by using native Python calculation.

---

### Run Tracking
**Files**: `orchestrator.py`, `lib/supabase_client.py`

**Purpose**: Persist the end-to-end state of each handoff run and each in-scope call.

**Tables**:
- `ae_handoff_runs`: one row per trigger-call handoff run
- `ae_handoff_run_calls`: one row per analyzed call inside that run

**Stored state includes**:
- trigger call metadata
- company/contact snapshot
- transcription status
- analysis status
- transcript judge / final judge verdicts
- final weighted score and qualification tier
- saved brief and dashboard paths

---

### Stage 7: AE Brief Agent
**File**: `stages/ae_brief_agent.py`

**Purpose**: Generates a formatted, evidence-based handoff brief for the Account Executive.

**Input**:
- `CompanyJourney` (company, contacts, calls)
- `score_result` (weighted score, tier, dimension table)
- BANTIC evidence per dimension

**Brief Sections**:
1. **Account Header**: Company, DM contact, meeting time, SDR, score
2. **ICP Fit**: Company size, location, DM verification, unknowns
3. **Current Process**: What tools they use today (from Current Process dimension)
4. **Evaluating Tools**: Active evaluation? Timeline? (from Timeline dimension)
5. **Pain / Need**: Actual problems from Need dimension (verbatim quote)
6. **Recommended Next Steps**: What AE should probe based on BANTIC gaps

**Anti-Hallucination Rules**:
- Quote directly from evidence — never infer
- If dimension scored 0, say "UNKNOWN — not discussed"
- Be specific (tool names, numbers, dates)
- Acknowledge gaps (if Authority low, say "unclear who DM is")
- Actionable (specific questions for AE)

**Output**:
- Formatted markdown brief
- Saved to `handoffs/<Company>_handoff.md`
- `ae_brief_sent = True` set in Supabase

**Cost**: $0.001 per brief (gpt-4o, ~400-500 tokens)

**Model**: gpt-4o (more capable than gpt-4o-mini for formatting and reasoning)

---

## Data Flow

```
HubSpot
  ├─ Call disposition (C - Meeting Scheduled)
  ├─ Call activity date / hs_timestamp
  ├─ Assigned owner
  ├─ Call outcome
  ├─ Recording URL
  ├─ Company details
  ├─ Contacts
  └─ Associated company ID
        ↓
Supabase calls table
  ├─ Idempotency flag (ae_brief_sent)
  ├─ Connected call metadata
  ├─ Raw transcript (from Deepgram)
  ├─ Cleaned transcript (from OpenAI)
  ├─ BANTIC scores (from analysis)
  └─ Evidence quotes
        ↓
Orchestrator (9 stages)
        ↓
Handoff brief + dashboard (local files + database flag)
```

## Key Design Decisions

### 1. Separate Directory
✓ **Rationale**: call-scoring-agent is stable and shouldn't be touched. AE Brief is an optional downstream feature that may evolve independently.

### 2. No LLM Scoring
✓ **Rationale**: Python calculates weighted score to avoid hallucination. OpenAI only used for analysis, labeling, and brief generation.

### 3. Evidence-Based
✓ **Rationale**: Every claim in the brief cites a verbatim transcript quote or explicit "UNKNOWN" if not discussed. Prevents made-up content.

### 4. Quality Gate (Future)
✓ **Rationale**: Only generate briefs when BANTIC data exists. Skip if all calls have no analysis.

### 5. Best Score Per Dimension
✓ **Rationale**: If company has 5 calls, show the strongest evidence for each dimension (not average). AE gets the best version of each story.

### 6. Synchronous Deepgram
✓ **Rationale**: Nova-3 returns results immediately. No need for async polling. Simplifies pipeline.

---

## Error Handling Strategy

| Stage | Error | Action |
|-------|-------|--------|
| 1 | No pending calls | Wait for next cycle (log as DEBUG) |
| 2 | Company not found | Log error, skip company |
| 2 | No calls for company | Log info, skip company |
| 3 | Empty recording URL | Skip call, continue to next |
| 3 | Deepgram API error | Mark as failed, log error, retry next cycle |
| 4 | OpenAI error | Log error, skip call |
| 4.1 | NVIDIA judge error/timeout | Log warning, keep cleaned transcript, continue |
| 5 | OpenAI error | Log error, skip call |
| 5 | JSON parse error | Try to extract from markdown wrapper, else skip |
| 5.5 | NVIDIA judge error/timeout | Log warning, keep original BANTIC score, continue |
| 6 | No analyzed calls | Log warning, skip company |
| 7 | OpenAI error | Log error, skip brief generation |
| 7 | File write error | Log error, skip save step |
| 7 | Supabase contact schema mismatch | Log error; current run may continue with in-memory contacts |

---

## Cost Analysis (per company)

Assuming 5 calls per company:

| Stage | Calls | Cost Each | Total |
|-------|-------|-----------|-------|
| 1-2 | 1 | $0.0005 | $0.0005 |
| 3 | 5 | $0.0043/min (avg 12 min) | $0.26 |
| 4 | 5 | $0.00015 | $0.00075 |
| 4.1 | 5 | NVIDIA API usage | varies |
| 4.5 | 1 | $0.00015 | ~$0.00015 |
| 5 | 5 | $0.0005 | $0.0025 |
| 5.5 | 5 | NVIDIA API usage | varies |
| 6 | - | $0 | $0 |
| 7 | 1 | $0.001 | $0.001 |
| **Total** | - | - | **~$0.26** |

→ **Deepgram dominates the cost** (~95%), not OpenAI.

---

## Security & Data Handling

- **No sensitive data in logs**: Transcripts stored in Supabase, not logged
- **API keys in .env only**: Never committed to git
- **Supabase row-level security**: Inherits from call-scoring-agent setup
- **No external storage**: Briefs saved locally only (can add HubSpot notes later)

---

## Observability

### Logging Levels
- **INFO**: Successful stage completions, key transitions
- **WARNING**: No data found, edge cases
- **ERROR**: API failures, exceptions

### Key Log Lines to Monitor
```
✓ Stage 1: Watcher found X pending calls
✓ Stage 2: Fetch complete: X contacts, Y calls
✓ Stage 3: Transcribed 5/5 calls
✓ Stage 4.1 complete: X approved, Y revised
✓ Stage 5: BANTIC analysis for 5 calls
✓ Stage 5.5 complete: X approved, Y revised
✓ Stage 6 complete: Overall Score X.X (Qualification Tier)
✓ Brief saved: handoffs/Company_handoff.md
```

### Metrics to Track
- Calls processed per day
- Average score per company
- Time per stage
- Error rate per stage
- Cost per company

---

## Future Enhancements

1. **Quality Gate**: Skip brief if BANTIC score ≤ 4.9 (Disqualified)
2. **HubSpot Notes**: Append brief to company notes in HubSpot
3. **Email Delivery**: Send brief to AE via email
4. **Analytics Dashboard**: Track brief generation metrics
5. **Custom Prompts**: Tenant-specific brief formats
6. **Multi-language**: Support non-English transcripts
7. **Competitor Intelligence**: Extract competitor mentions from calls
8. **Objection Library**: Track common objections per industry

---

**Last Updated**: 2026-05-01
**Version**: 1.1
