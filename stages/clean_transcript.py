import logging
import os
import json
from typing import Optional, Dict, Any
from openai import OpenAI
from lib.types import Call
from lib.supabase_client import update_call_fields

logger = logging.getLogger(__name__)

LABEL_SPEAKERS_PROMPT = """You are an expert B2B sales call analyst. Your job is to classify speakers in a transcript with ZERO errors.

## INPUT
The transcript below was produced by Deepgram Nova-3 (clean, punctuated, diarized). Speakers are labeled Speaker 0 and Speaker 1.

## CONTEXTUAL SIGNALS (use all of these before classifying)
- Named entities: {entities_summary}
- Sentiment: {sentiment_summary}
- Topics discussed: {topics}
- Company being called: {company_name}
- SDR name (if known): {sdr_name}
- Prospect name (if known): {prospect_name}

---

## CLASSIFICATION RULES

### Step 1 — Detect VOICEMAIL / IVR / RECEPTIONIST first
These are NOT the SDR and NOT the prospect. Label them [VOICEMAIL/IVR] or [RECEPTIONIST].

### Step 2 — Identify the SDR
The SDR is the OUTBOUND caller. Look for introductions ("This is [SDR] from Spyne"), qualifying questions, and the sales pitch about vehicle photography or AI merchandising.

### Step 3 — Identify the PROSPECT
The prospect is the INBOUND receiver. They answer the phone, react to the pitch, and mention dealership-specific roles (GM, Sales Manager).

### Step 4 — Use the Names
If Speaker 0 or 1 is addressed by {prospect_name} or {sdr_name}, use that as definitive proof.

---

## OUTPUT FORMAT
Return ONLY the relabeled transcript. No markdown, no explanations, no preamble.
Format each line exactly as:
[ROLE]: <dialogue>

Valid roles: SDR, PROSPECT, VOICEMAIL/IVR, RECEPTIONIST

TRANSCRIPT:
{transcript}"""


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)


def clean_transcript(call: Call, company_name: str = "Unknown", sdr_name: str = "Unknown", prospect_name: str = "Unknown") -> Optional[str]:
    """
    Stage 4: Clean Transcript Agent
    Uses OpenAI gpt-4o-mini to label speakers as [SDR], [PROSPECT], [VOICEMAIL/IVR].
    """
    if not call.raw_transcript:
        logger.warning(f"No raw transcript for {call.hubspot_call_id}")
        return None

    # Format context
    entities_str = json.dumps(call.deepgram_entities) if call.deepgram_entities else "None"
    sentiment_str = json.dumps(call.deepgram_sentiment) if call.deepgram_sentiment else "None"
    topics_str = json.dumps(call.deepgram_topics) if call.deepgram_topics else "None"

    prompt = LABEL_SPEAKERS_PROMPT.format(
        transcript=call.raw_transcript,
        entities_summary=entities_str,
        sentiment_summary=sentiment_str,
        topics=topics_str,
        company_name=company_name,
        sdr_name=sdr_name,
        prospect_name=prospect_name
    )

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            timeout=60
        )

        cleaned = response.choices[0].message.content.strip()
        return cleaned if cleaned else None

    except Exception as e:
        logger.error(f"OpenAI error cleaning transcript: {e}")
        return None


def clean_calls(calls: list, company_name: str = "Unknown", sdr_name: str = "Unknown", prospect_name: str = "Unknown") -> list:
    """Clean and label speakers in a batch of calls."""
    logger.info(f"→ Stage 4: Clean Transcript Agent for {len(calls)} calls")
    cleaned = []
    for call in calls:
        labeled = clean_transcript(call, company_name=company_name, sdr_name=sdr_name, prospect_name=prospect_name)
        if labeled:
            call.cleaned_transcript = labeled
            # Persist cleaned transcript to Supabase
            update_call_fields(call.hubspot_call_id, {
                "cleaned_transcript": call.cleaned_transcript
            })
            cleaned.append(call)
    logger.info(f"✓ Stage 4 complete: {len(cleaned)}/{len(calls)} cleaned")
    return cleaned
