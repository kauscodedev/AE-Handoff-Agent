import json
import logging
import os
from typing import Optional, List
import concurrent.futures
from openai import OpenAI
from lib.types import Call, BANTICScore
from lib.supabase_client import update_call_fields

logger = logging.getLogger(__name__)

BANTIC_PROMPT = """You are a senior sales qualification analyst. Analyze this B2B sales call transcript and score the qualification level for the BANTIC dimensions.

## BANTIC DIMENSIONS:
1. BUDGET (Score 0-3): Has a budget been mentioned or confirmed?
2. AUTHORITY (Score 0-3): Is the person a Decision Maker (DM) or Influencer?
3. NEED (Score 0-3): Is there a specific pain point or clear use case for Spyne?
4. TIMELINE (Score 0-3): When do they want to implement (e.g., "immediately", "next month", "no rush")?
5. IMPACT (Score 0-3): What is the business value or consequence of NOT solving the problem?
6. CURRENT PROCESS (Score 0-3): How are they doing vehicle photography today? (e.g., manual, another tool).

## SCORING SCALE (0-3):
- 0: UNKNOWN (Not discussed)
- 1: LOW (Vague mention, no specifics)
- 2: MEDIUM (Explicit mention with some detail)
- 3: HIGH (Complete clarity, confirmed facts)

## OUTPUT FORMAT:
Return ONLY a JSON object:
{{
  "budget": {{ "score": 0-3, "evidence": "...", "info_captured": "..." }},
  "authority": {{ "score": 0-3, "evidence": "...", "info_captured": "..." }},
  "need": {{ "score": 0-3, "evidence": "...", "info_captured": "..." }},
  "timeline": {{ "score": 0-3, "evidence": "...", "info_captured": "..." }},
  "impact": {{ "score": 0-3, "evidence": "...", "info_captured": "..." }},
  "current_process": {{ "score": 0-3, "evidence": "...", "info_captured": "..." }},
  "overall_summary": "Concise executive summary of call results",
  "sdr_coaching_note": "One specific tip for the SDR to improve qualification"
}}

TRANSCRIPT:
{transcript}"""


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)


def analyze_call(call: Call) -> Optional[BANTICScore]:
    """Stage 5: BANTIC Analysis Agent."""
    if not call.cleaned_transcript:
        return None

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": BANTIC_PROMPT.format(transcript=call.cleaned_transcript)}],
            response_format={"type": "json_object"},
            temperature=0,
            timeout=60
        )

        data = json.loads(response.choices[0].message.content)

        return BANTICScore(
            score_budget=data["budget"]["score"],
            budget_evidence=data["budget"]["evidence"],
            budget_info_captured=data["budget"]["info_captured"],
            score_authority=data["authority"]["score"],
            authority_evidence=data["authority"]["evidence"],
            authority_info_captured=data["authority"]["info_captured"],
            score_need=data["need"]["score"],
            need_evidence=data["need"]["evidence"],
            need_info_captured=data["need"]["info_captured"],
            score_timeline=data["timeline"]["score"],
            timeline_evidence=data["timeline"]["evidence"],
            timeline_info_captured=data["timeline"]["info_captured"],
            score_impact=data["impact"]["score"],
            impact_evidence=data["impact"]["evidence"],
            impact_info_captured=data["impact"]["info_captured"],
            score_current_process=data["current_process"]["score"],
            current_process_evidence=data["current_process"]["evidence"],
            current_process_info_captured=data["current_process"]["info_captured"],
            overall_summary=data["overall_summary"],
            sdr_coaching_note=data["sdr_coaching_note"]
        )

    except Exception as e:
        logger.error(f"Error in BANTIC analysis for {call.hubspot_call_id}: {e}")
        return None


def analyze_calls(calls: list) -> list:
    """Analyze a batch of calls in parallel."""
    logger.info(f"→ Stage 5: BANTIC Analysis Agent for {len(calls)} calls (Parallel)")

    analyzed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_call = {executor.submit(analyze_call, call): call for call in calls}
        for future in concurrent.futures.as_completed(future_to_call):
            call = future_to_call[future]
            try:
                score = future.result()
                if score:
                    call.bantic_score = score
                    # Persist BANTIC scores to Supabase
                    update_call_fields(call.hubspot_call_id, {
                        "score_budget": score.score_budget,
                        "score_authority": score.score_authority,
                        "score_need": score.score_need,
                        "score_timeline": score.score_timeline,
                        "score_impact": score.score_impact,
                        "score_current_process": score.score_current_process,
                        "budget_evidence": score.budget_evidence,
                        "authority_evidence": score.authority_evidence,
                        "need_evidence": score.need_evidence,
                        "timeline_evidence": score.timeline_evidence,
                        "impact_evidence": score.impact_evidence,
                        "current_process_evidence": score.current_process_evidence,
                        "budget_info_captured": score.budget_info_captured,
                        "authority_info_captured": score.authority_info_captured,
                        "need_info_captured": score.need_info_captured,
                        "timeline_info_captured": score.timeline_info_captured,
                        "impact_info_captured": score.impact_info_captured,
                        "current_process_info_captured": score.current_process_info_captured,
                        "overall_summary": score.overall_summary,
                        "sdr_coaching_note": score.sdr_coaching_note,
                        "analysis_status": "complete"
                    })
                    analyzed.append((call, score))
            except Exception as e:
                logger.error(f"Error analyzing call {call.hubspot_call_id}: {e}")

    logger.info(f"✓ Stage 5 complete: {len(analyzed)}/{len(calls)} analyzed")
    return analyzed
