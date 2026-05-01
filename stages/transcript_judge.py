"""
Transcript Judge Stage (4.1)
Uses GLM-4.7 with extended thinking to verify speaker labels ([SDR]/[PROSPECT]) are correct.
Catches global swaps and individual turn mismatches. Logs all feedback.
"""

import os
import json
import re
import logging
from typing import List, Dict, Any, Tuple
from openai import OpenAI

from lib.types import Call
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

JUDGE_SYSTEM_PROMPT = """You are a senior call center quality analyst reviewing speaker labels on B2B sales calls.

Your role: catch clear speaker misidentifications, not nitpick ambiguous turns. Be fair.

Context:
- SDR = the one who initiated the call, introduces themselves, pitches Spyne's photo solution
- PROSPECT = received the unexpected call, typically from automotive/dealership
- VOICEMAIL/IVR = automated system ("You've reached...", "Press 1...", "Our hours are...")
- RECEPTIONIST = human gatekeeper ("Who's calling?", "Let me transfer you", "They're not available")

Review each labeled turn against expected role behavior. Identify:
1. GLOBAL SWAPS: SDR and PROSPECT labels are systematically reversed throughout
2. TURN CORRECTIONS: Specific turns with wrong labels (voicemail as SDR, receptionist as PROSPECT, etc.)

Return JSON only:
{
  "verdict": "approved" | "revised",
  "reasoning": "one sentence explanation",
  "global_swaps": [
    {"from": "SDR", "to": "PROSPECT"},
    {"from": "PROSPECT", "to": "SDR"}
  ],
  "turn_corrections": [
    {"turn_index": 2, "corrected_label": "VOICEMAIL/IVR", "reason": "automated greeting"}
  ]
}

If verdict is "approved", both swap and correction arrays are empty."""


def _split_thinking(content: str) -> Tuple[str, str]:
    """Parse GLM-4.7 response into thinking and answer sections."""
    match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
    thinking = match.group(1).strip() if match else ""
    answer = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    return thinking, answer


def _truncate_transcript(transcript: str, max_chars: int = 3000, max_turns: int = 100) -> str:
    """Truncate transcript to first N turns or X chars, whichever comes first."""
    lines = transcript.split('\n')
    truncated_lines = lines[:max_turns]
    text = '\n'.join(truncated_lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n..."
    return text


def _judge_transcript(call: Call) -> Dict[str, Any]:
    """
    Judge a single call's transcript speaker labels using GLM-4.7 with thinking.
    Returns judgment dict with verdict, corrections, and reasoning.
    """
    if not call.cleaned_transcript or not call.raw_transcript:
        return {"error": "Missing cleaned or raw transcript"}

    # Truncate for token efficiency (critical labels are established early)
    raw_excerpt = _truncate_transcript(call.raw_transcript)
    cleaned_excerpt = _truncate_transcript(call.cleaned_transcript)

    review_prompt = f"""Review this call's speaker labels for accuracy:

RAW TRANSCRIPT (Deepgram diarization):
{raw_excerpt}

CLEANED TRANSCRIPT (Stage 4 relabeled):
{cleaned_excerpt}

Verify the speaker-to-role mapping is correct. Look for:
- Are SDR and PROSPECT labels systematically swapped?
- Are any turns clearly mislabeled (voicemail as SDR, receptionist as PROSPECT, etc.)?"""

    try:
        client = _get_judge_client()
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": review_prompt}
            ],
            temperature=0,
            max_tokens=2048,
            response_format={"type": "json_object"},
            extra_body={"chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}},
            timeout=90,
        )

        response_content = completion.choices[0].message.content
        if response_content is None:
            return {"error": "Empty response from judge API"}

        thinking, answer = _split_thinking(response_content)

        judgment = json.loads(answer)
        judgment["judge_thinking"] = thinking[:500]

        return judgment

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse judge response for {call.hubspot_call_id}: {e}")
        return {"error": "JSON parse failed"}
    except Exception as e:
        logger.error(f"Judge error for {call.hubspot_call_id}: {e}")
        return {"error": str(e)}


def _apply_transcript_corrections(cleaned_transcript: str, judgment: Dict) -> str:
    """
    Apply corrections to cleaned_transcript using deterministic replacements.
    Never rewrites dialogue content — only corrects labels.
    """
    lines = cleaned_transcript.split('\n')

    # Apply turn_corrections first (indexed line replacement)
    for corr in judgment.get('turn_corrections', []):
        idx = corr.get('turn_index')
        if idx is not None and 0 <= idx < len(lines):
            corrected_label = corr.get('corrected_label')
            lines[idx] = re.sub(r'^\[([^\]]+)\]:', f'[{corrected_label}]:', lines[idx])

    result = '\n'.join(lines)

    # Apply global_swaps with temp placeholder (avoid double-replacement)
    for swap in judgment.get('global_swaps', []):
        from_label = swap['from']
        to_label = swap['to']
        result = result.replace(f'[{from_label}]:', f'[__TEMP_{from_label}__]:')

    for swap in judgment.get('global_swaps', []):
        from_label = swap['from']
        to_label = swap['to']
        result = result.replace(f'[__TEMP_{from_label}__]:', f'[{to_label}]:')

    return result


def _log_judge_feedback(call: Call, judgment: Dict):
    """Log judge feedback to logs/transcript_judge_feedback.jsonl"""
    os.makedirs("logs", exist_ok=True)

    corrections = []
    for swap in judgment.get('global_swaps', []):
        corrections.append({
            "type": "global_swap",
            "from": swap['from'],
            "to": swap['to']
        })
    for corr in judgment.get('turn_corrections', []):
        corrections.append({
            "type": "turn_correction",
            "turn_index": corr.get('turn_index'),
            "corrected_label": corr.get('corrected_label'),
            "reason": corr.get('reason', '')
        })

    feedback_entry = {
        "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
        "call_id": call.hubspot_call_id,
        "verdict": judgment.get("verdict", "unknown"),
        "reasoning": judgment.get("reasoning", ""),
        "corrections_applied": corrections,
        "judge_thinking": judgment.get("judge_thinking", "")[:500]
    }

    try:
        with open("logs/transcript_judge_feedback.jsonl", "a") as f:
            f.write(json.dumps(feedback_entry) + "\n")
    except Exception as e:
        logger.error(f"Failed to write transcript judge feedback: {e}")


def judge_transcripts(calls: List[Call]) -> List[Call]:
    """
    Stage 4.1: Transcript Judge reviews speaker labeling for accuracy.

    Takes list of Call objects with raw_transcript and cleaned_transcript.
    Uses GLM-4.7 with thinking to verify labels. Corrects global swaps and turn mismatches.
    Logs verdict and corrections. Returns possibly-mutated calls with updated cleaned_transcript.
    """
    if not calls:
        logger.info("→ Stage 4.1: Transcript Judge — no calls to review")
        return calls

    logger.info(f"→ Stage 4.1: Transcript Judge reviewing {len(calls)} calls")

    approved_count = 0
    revised_count = 0

    for call in calls:
        if not call.cleaned_transcript or not call.raw_transcript:
            logger.warning(f"  ⚠️ {call.hubspot_call_id[:12]}: missing transcript")
            approved_count += 1
            continue

        original_transcript = call.cleaned_transcript

        # Run judgment
        judgment = _judge_call(call)

        if judgment.get("error"):
            logger.warning(f"  ⚠️ Judge error for {call.hubspot_call_id}: {judgment['error']}")
            approved_count += 1
            continue

        # Check if revisions needed
        has_swaps = bool(judgment.get('global_swaps'))
        has_corrections = bool(judgment.get('turn_corrections'))

        if judgment.get('verdict') == 'revised' and (has_swaps or has_corrections):
            # Apply corrections
            corrected_transcript = _apply_transcript_corrections(original_transcript, judgment)
            call.cleaned_transcript = corrected_transcript

            # Persist to Supabase
            update_call_fields(call.hubspot_call_id, {"cleaned_transcript": corrected_transcript})

            # Log feedback
            _log_judge_feedback(call, judgment)

            revised_count += 1
            correction_summary = []
            if has_swaps:
                for swap in judgment.get('global_swaps', []):
                    correction_summary.append(f"{swap['from']}↔{swap['to']}")
            if has_corrections:
                correction_summary.append(f"{len(judgment.get('turn_corrections', []))} turns")
            logger.info(f"  ✏️ {call.hubspot_call_id[:12]}: {', '.join(correction_summary)}")
        else:
            # Approved
            _log_judge_feedback(call, judgment)
            approved_count += 1

    logger.info(f"✓ Stage 4.1 complete: {approved_count} approved, {revised_count} revised")

    return calls


def _judge_call(call: Call) -> Dict[str, Any]:
    """Wrapper for backward compatibility."""
    return _judge_transcript(call)
