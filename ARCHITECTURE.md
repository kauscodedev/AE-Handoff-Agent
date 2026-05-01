# AE Handoff Brief Agent — Architecture Deep Dive

## Overview

The AE Handoff Brief Agent is a standalone 7-stage multi-agent pipeline that transforms raw call data into evidence-based Account Executive handoff briefs. It operates independently from call-scoring-agent but uses the same Supabase database for call analysis data.

## 7-Stage Pipeline

### Stage 1: HubSpot Watcher
**File**: `stages/watcher.py`

**Purpose**: Continuously polls HubSpot for new calls with "C - Meeting Scheduled" disposition that haven't been briefed yet.

**Input**: 
- HubSpot API query: calls where `hs_call_disposition = "C - Meeting Scheduled"` and `hs_timestamp` is within the watcher window
- Supabase idempotency check: skip call IDs where `ae_brief_sent = True`

**Output**:
- List of pending call objects: `[{hubspot_call_id, hubspot_company_id, call_date, activity_date, assigned_to, call_outcome, recording_url}, ...]`

**Frequency**: Every 60 seconds (configurable)

**Cost**: Free (HubSpot API)

---

### Stage 2: Fetch Agent
**File**: `stages/fetch_agent.py`

**Purpose**: Gathers complete company context by fetching from HubSpot and Supabase.

**Input**: 
- `company_id` from Stage 1 trigger call

**Fetches**:
- Company details: name, headcount, location
- All contacts at company: name, title, email
- All calls for company from Supabase (with BANTIC analysis data)
- Call recordings, transcripts, and scores

**Output**:
- `CompanyJourney` object with:
  - `company`: Company details
  - `contacts`: List of Contact objects
  - `calls`: List of all calls with BANTIC scores
  - `dm_contact`: Identified decision maker (if any)

**Cost**: ~$0.0005 (HubSpot API calls)

**Error Handling**: 
- Returns None if company not found
- Returns empty journey if no calls found

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
  ├─ Company details
  ├─ Contacts
  └─ SDR owner name
        ↓
Supabase calls table
  ├─ Recording URL (from Deepgram submission)
  ├─ Raw transcript (from Deepgram)
  ├─ BANTIC scores (from analysis)
  └─ Evidence quotes
        ↓
Orchestrator (7 stages)
        ↓
Handoff brief (Markdown file + database flag)
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
| 5 | OpenAI error | Log error, skip call |
| 5 | JSON parse error | Try to extract from markdown wrapper, else skip |
| 6 | No analyzed calls | Log warning, skip company |
| 7 | OpenAI error | Log error, skip brief generation |
| 7 | File write error | Log error, skip save step |

---

## Cost Analysis (per company)

Assuming 5 calls per company:

| Stage | Calls | Cost Each | Total |
|-------|-------|-----------|-------|
| 1-2 | 1 | $0.0005 | $0.0005 |
| 3 | 5 | $0.0043/min (avg 12 min) | $0.26 |
| 4 | 5 | $0.00015 | $0.00075 |
| 5 | 5 | $0.0005 | $0.0025 |
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
✓ Stage 5: BANTIC analysis for 5 calls
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

**Last Updated**: 2026-04-28
**Version**: 1.0
