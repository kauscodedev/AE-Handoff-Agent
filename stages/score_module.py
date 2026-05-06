import logging
import json
from typing import Dict, List, Tuple, Optional
from lib.types import BANTICScore, Call
from lib.supabase_client import update_call_fields

logger = logging.getLogger(__name__)

DIMENSION_LABELS = {
    "budget": "Budget",
    "authority": "Authority",
    "need": "Need",
    "timeline": "Timeline",
    "impact": "Impact",
    "current_process": "Current Process"
}

DIMENSION_FIELDS = {
    "budget": ("score_budget", "budget_evidence", "budget_info_captured"),
    "authority": ("score_authority", "authority_evidence", "authority_info_captured"),
    "need": ("score_need", "need_evidence", "need_info_captured"),
    "timeline": ("score_timeline", "timeline_evidence", "timeline_info_captured"),
    "impact": ("score_impact", "impact_evidence", "impact_info_captured"),
    "current_process": ("score_current_process", "current_process_evidence", "current_process_info_captured"),
}


def calculate_weighted_score(b: float, a: float, n: float, t: float, i: float, cp: float) -> float:
    """
    Stage 6: Score Module (Python, no LLM)
    Calculates weighted BANTIC score: (B×5 + A×20 + N×25 + T×15 + I×15 + CP×20) / 30
    """
    score = (b*5 + a*20 + n*25 + t*15 + i*15 + cp*20) / 30
    return round(score, 1)


def get_qualification_tier(score: float) -> str:
    """Map weighted score to qualification tier."""
    if score >= 8.1:
        return "Very High Intent"
    elif score >= 8.0:
        return "High Intent"
    elif score >= 5.0:
        return "Qualified"
    else:
        return "Disqualified"


def find_best_scores_per_dimension(calls_with_scores: List[Tuple[Call, BANTICScore]]) -> Dict[str, Dict]:
    """
    Find the best (highest) score for each dimension across all calls.
    Also identifies "What's Missing" based on the gap to a perfect score.
    """
    best_scores = {}

    for dim_key, (score_field, evidence_field, info_field) in DIMENSION_FIELDS.items():
        best_score = 0
        best_evidence = None
        best_call_id = None
        best_info = None

        for call, score_obj in calls_with_scores:
            current_score = getattr(score_obj, score_field) or 0
            if current_score > best_score:
                best_score = current_score
                best_evidence = getattr(score_obj, evidence_field)
                best_info = getattr(score_obj, info_field)
                best_call_id = call.hubspot_call_id

        # Logic for "What's Missing"
        missing_info = "Complete"
        if best_score == 0:
            missing_info = f"Everything. {DIMENSION_LABELS[dim_key]} was never raised in any call."
        elif best_score == 1:
            missing_info = "Substance. Topic was mentioned but remained vague or non-committal."
        elif best_score == 2:
            missing_info = "Quantification. Details are clear but lack specific numbers or event-driven timelines."

        best_scores[dim_key] = {
            "label": DIMENSION_LABELS[dim_key],
            "best_score": best_score,
            "best_evidence": best_evidence or "Not captured",
            "best_info": best_info or "Not discussed",
            "whats_missing": missing_info,
            "call_id": best_call_id
        }

    return best_scores


def _markdown_cell(value: object) -> str:
    """Keep deterministic markdown tables readable inside HubSpot text fields."""
    text = str(value or "UNKNOWN").replace("\n", " ").replace("|", "\\|").strip()
    return text or "UNKNOWN"


def _call_notes_summary(call: Call) -> Optional[Dict]:
    notes = getattr(call, "call_notes", None)
    if not notes:
        return None
    return {
        "call_id": call.hubspot_call_id,
        "notes": notes,
    }


def compute_overall_weighted_score(best_scores: Dict[str, Dict]) -> Tuple[float, str]:
    """
    Calculate overall weighted score from best dimension scores.
    Returns: (weighted_score, qualification_tier)
    """
    b = best_scores["budget"]["best_score"]
    a = best_scores["authority"]["best_score"]
    n = best_scores["need"]["best_score"]
    t = best_scores["timeline"]["best_score"]
    i = best_scores["impact"]["best_score"]
    cp = best_scores["current_process"]["best_score"]

    weighted = calculate_weighted_score(b, a, n, t, i, cp)
    tier = get_qualification_tier(weighted)

    return weighted, tier


def generate_per_call_matrix(calls_with_scores: List[Tuple[Call, BANTICScore]]) -> List[Dict]:
    """
    Generates a matrix of scores for every call (similar to reference image 1).
    """
    matrix = []
    for call, score_obj in calls_with_scores:
        call_entry = {
            "call_id": call.hubspot_call_id,
            "date": call.call_date,
            "scores": {
                "budget": score_obj.score_budget,
                "authority": score_obj.score_authority,
                "need": score_obj.score_need,
                "timeline": score_obj.score_timeline,
                "impact": score_obj.score_impact,
                "current_process": score_obj.score_current_process
            },
            "weighted": calculate_weighted_score(
                score_obj.score_budget or 0,
                score_obj.score_authority or 0,
                score_obj.score_need or 0,
                score_obj.score_timeline or 0,
                score_obj.score_impact or 0,
                score_obj.score_current_process or 0
            )
        }
        matrix.append(call_entry)
    return matrix


def generate_bantic_snapshot(calls_with_scores: List[Tuple[Call, BANTICScore]], best_scores: Dict[str, Dict]) -> Dict:
    """Build the full qualification context used by the final AE handoff."""
    dimensions = []
    for dim_key, data in best_scores.items():
        dimensions.append({
            "dimension": data["label"],
            "score": data["best_score"],
            "evidence": data["best_evidence"],
            "info_captured": data["best_info"],
            "gap_or_follow_up": data["whats_missing"],
            "source_call_id": data["call_id"],
        })

    call_summaries = []
    for call, score_obj in calls_with_scores:
        call_summaries.append({
            "call_id": call.hubspot_call_id,
            "call_date": call.call_date,
            "call_outcome": getattr(call, "call_outcome", None),
            "assigned_to": getattr(call, "assigned_to", None),
            "call_notes_available": bool(getattr(call, "call_notes", None)),
            "overall_summary": score_obj.overall_summary,
            "sdr_coaching_note": score_obj.sdr_coaching_note,
            "scores": {
                "budget": score_obj.score_budget,
                "authority": score_obj.score_authority,
                "need": score_obj.score_need,
                "timeline": score_obj.score_timeline,
                "impact": score_obj.score_impact,
                "current_process": score_obj.score_current_process,
            },
            "info_captured": {
                "budget": score_obj.budget_info_captured,
                "authority": score_obj.authority_info_captured,
                "need": score_obj.need_info_captured,
                "timeline": score_obj.timeline_info_captured,
                "impact": score_obj.impact_info_captured,
                "current_process": score_obj.current_process_info_captured,
            },
            "evidence": {
                "budget": score_obj.budget_evidence,
                "authority": score_obj.authority_evidence,
                "need": score_obj.need_evidence,
                "timeline": score_obj.timeline_evidence,
                "impact": score_obj.impact_evidence,
                "current_process": score_obj.current_process_evidence,
            },
            "final_judge_verdict": getattr(call, "final_judge_verdict", None),
            "final_judge_feedback": getattr(call, "final_judge_feedback", None),
        })

    return {
        "dimensions": dimensions,
        "call_summaries": call_summaries,
        "call_notes": [
            item for item in (_call_notes_summary(call) for call, _score in calls_with_scores) if item
        ],
    }


def format_bantic_snapshot_table(snapshot: Dict) -> str:
    """Render the auditable BANTIC table that is written to HubSpot."""
    header = "| Dimension | Best Score | Evidence | Info Captured | Gap / AE Follow-up |\n"
    sep = "|---|---:|---|---|---|\n"
    rows = []
    for item in snapshot.get("dimensions", []):
        rows.append(
            f"| {_markdown_cell(item.get('dimension'))} "
            f"| {_markdown_cell(str(item.get('score', 0)) + '/3')} "
            f"| {_markdown_cell(item.get('evidence'))} "
            f"| {_markdown_cell(item.get('info_captured'))} "
            f"| {_markdown_cell(item.get('gap_or_follow_up'))} |\n"
        )
    return header + sep + "".join(rows)


def format_bantic_snapshot_prompt(snapshot: Dict) -> str:
    """Give Stage 7 complete BANTIC context without relying on markdown truncation."""
    return json.dumps(snapshot, default=str, ensure_ascii=False, indent=2)


def score_company_journey(calls_with_scores: List[Tuple[Call, BANTICScore]], trigger_call_id: Optional[str] = None) -> Dict:
    """
    Stage 6: Score Module
    """
    logger.info(f"→ Stage 6: Score Module for {len(calls_with_scores)} analyzed calls")

    if not calls_with_scores:
        logger.warning("No analyzed calls provided")
        return None

    # Find best scores per dimension
    best_scores = find_best_scores_per_dimension(calls_with_scores)

    # Calculate overall weighted score
    weighted_score, tier = compute_overall_weighted_score(best_scores)

    # Generate per-call matrix (Reference Image 1)
    per_call_matrix = generate_per_call_matrix(calls_with_scores)
    bantic_snapshot = generate_bantic_snapshot(calls_with_scores, best_scores)

    # Persist weighted score and tier to Supabase (on trigger call)
    if trigger_call_id:
        update_call_fields(trigger_call_id, {
            "bantic_weighted_score": weighted_score,
            "bantic_qualification_tier": tier
        })

    result = {
        "best_scores": best_scores,
        "weighted_score": weighted_score,
        "qualification_tier": tier,
        "num_calls_analyzed": len(calls_with_scores),
        "per_call_matrix": per_call_matrix,
        "bantic_snapshot": bantic_snapshot,
        "bantic_snapshot_markdown": format_bantic_snapshot_table(bantic_snapshot),
        "bantic_snapshot_prompt": format_bantic_snapshot_prompt(bantic_snapshot),
        "dimensions_table": format_dimensions_table(best_scores)
    }

    logger.info(f"✓ Stage 6 complete: Overall Score {weighted_score} ({tier})")
    return result


def format_dimensions_table(best_scores: Dict[str, Dict]) -> str:
    """Format dimension scores as a markdown table including 'What's Missing'."""
    header = "| Dimension | Best Score | Best Evidence | What's Missing |\n"
    sep = "|---|---|---|---|\n"
    rows = []

    for dim_key, data in best_scores.items():
        dim_label = data["label"]
        score = data["best_score"]
        evidence = data["best_evidence"][:100] + "..." if len(data["best_evidence"]) > 100 else data["best_evidence"]
        missing = data["whats_missing"]

        row = f"| {dim_label} | {score}/3 | {evidence} | {missing} |\n"
        rows.append(row)

    return header + sep + "".join(rows)
