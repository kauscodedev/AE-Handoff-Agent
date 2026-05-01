"""
Final Judge Stage (5.5)
Uses GLM-4.7 with extended thinking to review BANTIC scores for accuracy.
Non-overcritical: only revises clearly wrong scores. Logs all feedback.
"""

import os
import json
import re
import logging
from datetime import datetime
from typing import List, Tuple, Dict, Any
from openai import OpenAI

from lib.types import Call, BANTICScore
from lib.supabase_client import update_call_fields

logger = logging.getLogger(__name__)

# NVIDIA API client for GLM-4.7 with thinking (lazy-loaded)
_judge_client = None
MODEL = "z-ai/glm4.7"

def _get_judge_client():
    """Lazy-load the NVIDIA API client."""
    global _judge_client
    if _judge_client is None:
        api_key = os.environ.get("NVIDIA_API_KEY")
        if not api_key:
            raise ValueError(
                "NVIDIA_API_KEY environment variable not set. "
                "Add it to your .env file: NVIDIA_API_KEY=nvapi-..."
            )
        _judge_client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key
        )
    return _judge_client

JUDGE_SYSTEM_PROMPT = """You are a senior B2B sales analyst reviewing BANTIC scores assigned by an AI during sales call analysis.

Your role: catch clear mistakes, not nitpick borderline calls. Be fair and give the original analysis the benefit of the doubt.

BANTIC Scoring Scale:
- 0 = Not discussed at all
- 1 = Discussed but vague / prospect deflected
- 2 = Good — clear, substantive response with real information
- 3 = Excellent — highly specific (numbers, dates, tool names, budget figures, measurable metrics)

Rules for revision:
1. Only revise a score if it is clearly wrong:
   - The evidence plainly does not support the score (e.g., score=2 but evidence says "vague")
   - OR the transcript shows the topic was never discussed but score > 0
   - OR the score is off by 2+ points (e.g., 3 when evidence warrants 1)

2. Do NOT:
   - Lower a score just because you'd phrase the evidence differently
   - Require 3 ("Excellent") unless evidence genuinely has concrete specifics
   - Increase a score beyond what the evidence supports

3. When uncertain: approve the original score. Err toward giving credit.

Return a JSON object with this exact structure:
{
  "verdict": "approved" | "revised",
  "overall_comment": "one sentence assessment",
  "dimensions": {
    "budget":          {"verdict": "approved"|"revised", "suggested_score": 0-3, "suggested_evidence": "exact quote or summary", "reason": "brief explanation"},
    "authority":       {"verdict": "...", ...},
    "need":            {"verdict": "...", ...},
    "timeline":        {"verdict": "...", ...},
    "impact":          {"verdict": "...", ...},
    "current_process": {"verdict": "...", ...}
  }
}

For dimensions marked "approved", set suggested_score = original score and suggested_evidence = original evidence.
For dimensions marked "revised", explain the specific issue in "reason"."""


def _split_thinking(content: str) -> Tuple[str, str]:
    """Parse GLM-4.7 response into thinking and answer sections."""
    # GLM-4.7 wraps thinking in <think>...</think>
    match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
    thinking = match.group(1).strip() if match else ""
    # Remove thinking block to get clean answer
    answer = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    return thinking, answer


def _format_score_for_review(call_id: str, score: BANTICScore, cleaned_transcript: str) -> str:
    """Format the BANTIC score review request."""
    dimensions = [
        ("budget", score.score_budget, score.budget_evidence, score.budget_info_captured),
        ("authority", score.score_authority, score.authority_evidence, score.authority_info_captured),
        ("need", score.score_need, score.need_evidence, score.need_info_captured),
        ("timeline", score.score_timeline, score.timeline_evidence, score.timeline_info_captured),
        ("impact", score.score_impact, score.impact_evidence, score.impact_info_captured),
        ("current_process", score.score_current_process, score.current_process_evidence, score.current_process_info_captured),
    ]

    dims_text = ""
    for dim_name, dim_score, evidence, info_captured in dimensions:
        dims_text += f"\n{dim_name.upper()} (Score: {dim_score}/3)\n"
        dims_text += f"  Evidence: {evidence[:200]}\n"
        dims_text += f"  Info captured: {info_captured[:200]}\n"

    return f"""Review this BANTIC analysis for call {call_id[:12]}:

TRANSCRIPT:
{cleaned_transcript[:2000]}
...

ORIGINAL ANALYSIS:
{dims_text}

OVERALL SUMMARY:
{score.overall_summary}

ASSESSMENT:
Review each dimension above. Only revise if the score is clearly wrong (evidence doesn't support it,
or topic was never discussed but scored > 0). Be fair — approve borderline scores."""


def _judge_call(call: Call, score: BANTICScore) -> Dict[str, Any]:
    """
    Judge a single call's BANTIC scores using GLM-4.7 with thinking.
    Returns judgment dict with verdict, changes, and reasoning.
    """
    if not call.cleaned_transcript:
        return {"error": "No cleaned transcript available"}

    # Format review request
    review_prompt = _format_score_for_review(call.hubspot_call_id, score, call.cleaned_transcript)

    try:
        # Non-streaming call to GLM-4.7 (simpler for JSON parsing)
        client = _get_judge_client()
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": review_prompt}
            ],
            temperature=0,
            max_tokens=4096,
            response_format={"type": "json_object"},
            extra_body={"chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}},
            timeout=30,
        )

        # Parse response
        response_content = completion.choices[0].message.content
        thinking, answer = _split_thinking(response_content)

        # Parse JSON judgment
        judgment = json.loads(answer)
        judgment["judge_thinking"] = thinking[:500]  # Truncate thinking for logging

        return judgment

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse judge response for {call.hubspot_call_id}: {e}")
        return {"error": "JSON parse failed"}
    except Exception as e:
        logger.error(f"Judge error for {call.hubspot_call_id}: {e}")
        return {"error": str(e)}


def _apply_revisions(call: Call, score: BANTICScore, judgment: Dict) -> List[str]:
    """
    Apply judge revisions to the BANTICScore object.
    Returns list of field names that were changed.
    """
    if judgment.get("error"):
        return []

    changes = []
    dimension_fields = {
        "budget": ("score_budget", "budget_evidence"),
        "authority": ("score_authority", "authority_evidence"),
        "need": ("score_need", "need_evidence"),
        "timeline": ("score_timeline", "timeline_evidence"),
        "impact": ("score_impact", "impact_evidence"),
        "current_process": ("score_current_process", "current_process_evidence"),
    }

    for dim_name, (score_field, evidence_field) in dimension_fields.items():
        dim_verdict = judgment.get("dimensions", {}).get(dim_name, {})
        if dim_verdict.get("verdict") == "revised":
            new_score = dim_verdict.get("suggested_score")
            new_evidence = dim_verdict.get("suggested_evidence")

            if new_score is not None:
                old_score = getattr(score, score_field)
                if old_score != new_score:
                    setattr(score, score_field, new_score)
                    changes.append(score_field)

            if new_evidence:
                old_evidence = getattr(score, evidence_field)
                if old_evidence != new_evidence:
                    setattr(score, evidence_field, new_evidence)
                    changes.append(evidence_field)

    return changes


def _log_judge_feedback(
    call: Call,
    company_name: str,
    judgment: Dict,
    changes: List[str],
    original_scores: Dict,
    final_scores: Dict
):
    """Log judge feedback to logs/judge_feedback.jsonl"""
    os.makedirs("logs", exist_ok=True)

    feedback_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "company_name": company_name,
        "call_id": call.hubspot_call_id,
        "verdict": judgment.get("verdict", "unknown"),
        "original_scores": original_scores,
        "final_scores": final_scores,
        "changes": changes,
        "overall_comment": judgment.get("overall_comment", ""),
        "judge_thinking": judgment.get("judge_thinking", "")[:500]
    }

    # Append to JSONL log
    try:
        with open("logs/judge_feedback.jsonl", "a") as f:
            f.write(json.dumps(feedback_entry) + "\n")
    except Exception as e:
        logger.error(f"Failed to write judge feedback: {e}")


def judge_bantic_scores(
    calls_with_scores: List[Tuple[Call, BANTICScore]],
    company_name: str = ""
) -> List[Tuple[Call, BANTICScore]]:
    """
    Stage 5.5: Final Judge reviews BANTIC scores for accuracy.

    Takes list of (Call, BANTICScore) tuples. Reviews each with GLM-4.7 thinking model.
    Only revises clearly wrong scores. Logs all feedback. Returns possibly modified list.
    """
    if not calls_with_scores:
        logger.info("→ Stage 5.5: Final Judge — no calls to review")
        return calls_with_scores

    logger.info(f"→ Stage 5.5: Final Judge reviewing {len(calls_with_scores)} calls")

    approved_count = 0
    revised_count = 0

    for call, score in calls_with_scores:
        # Capture original scores for logging
        original_scores = {
            "budget": score.score_budget,
            "authority": score.score_authority,
            "need": score.score_need,
            "timeline": score.score_timeline,
            "impact": score.score_impact,
            "current_process": score.score_current_process,
        }

        # Run judgment
        judgment = _judge_call(call, score)
        call.final_judge_verdict = judgment.get("verdict") if judgment else None
        call.final_judge_feedback = judgment

        if judgment.get("error"):
            logger.warning(f"  ⚠️ Judge error for {call.hubspot_call_id}: {judgment['error']}")
            approved_count += 1
            continue

        # Apply revisions if any
        changes = _apply_revisions(call, score, judgment)

        # Capture final scores for logging
        final_scores = {
            "budget": score.score_budget,
            "authority": score.score_authority,
            "need": score.score_need,
            "timeline": score.score_timeline,
            "impact": score.score_impact,
            "current_process": score.score_current_process,
        }

        # Log feedback
        _log_judge_feedback(
            call=call,
            company_name=company_name,
            judgment=judgment,
            changes=changes,
            original_scores=original_scores,
            final_scores=final_scores
        )

        # Persist revisions to Supabase if any
        if changes:
            fields_to_update = {}
            for field_name in changes:
                fields_to_update[field_name] = getattr(score, field_name)
            update_call_fields(call.hubspot_call_id, fields_to_update)
            revised_count += 1
            logger.info(f"  ✏️ {call.hubspot_call_id[:12]}: {', '.join(changes)}")
        else:
            approved_count += 1

    logger.info(f"✓ Stage 5.5 complete: {approved_count} approved, {revised_count} revised")

    return calls_with_scores
