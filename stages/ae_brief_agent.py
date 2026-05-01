import logging
import os
import json
from typing import Optional, Dict, Any
from openai import OpenAI
from lib.types import CompanyJourney
from lib.supabase_client import update_handoff_sent
from lib.hubspot_client import update_company_property
from lib.html_generator import generate_html_brief, save_html_brief

logger = logging.getLogger(__name__)

AE_HANDOFF_PROMPT = """You are an AE handoff brief specialist. Generate a professional, data-driven brief based on the BANTIC analysis of {num_calls} SDR calls with {company_name}.

GROUND RULES:
- Use UNKNOWN if a dimension is missing (score 0).
- Quote evidence directly.
- Be actionable and concise.
- Each section should be 2-3 sentences max.

OUTPUT REQUIRED:
Return ONLY a valid JSON object with exactly these 5 keys:
{{
  "icp_fit": "Summary of company size, location, and DM status.",
  "current_process": "What tools/workflows they use today. Reference what was discussed.",
  "evaluating_tools": "Are they actively evaluating alternatives? What's the trigger? Timeline?",
  "pain_need": "The specific business problem(s) identified. Cite evidence.",
  "next_steps": "Specific gaps (Budget/Impact/etc.) the AE should address."
}}

COMPANY CONTEXT:
- Name: {company_name}
- Employees: {employees}
- Location: {location}
- DM: {dm_contact}
- Meeting Time: {meeting_time}
- SDR: {sdr_name}
- Overall Score: {weighted_score}/10 ({qualification_tier})

BANTIC SCORES:
{dimensions_table}
"""


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)


def generate_ae_brief(journey: CompanyJourney, score_result: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Stage 7: AE Handoff Brief Agent
    Generates structured brief sections (JSON) and HTML dashboard.
    Returns dict with 5 keys: icp_fit, current_process, evaluating_tools, pain_need, next_steps
    """
    logger.info(f"→ Stage 7: AE Brief Agent for {journey.company.name}")

    # Extract scores
    weighted_score = score_result["weighted_score"]
    tier = score_result["qualification_tier"]
    dim_table = score_result["dimensions_table"]

    # Format prompt
    prompt = AE_HANDOFF_PROMPT.format(
        num_calls=len(journey.calls),
        company_name=journey.company.name,
        employees=journey.company.employees or "UNKNOWN",
        location=journey.company.location or "UNKNOWN",
        weighted_score=weighted_score,
        qualification_tier=tier,
        dm_contact=journey.dm_contact.name if journey.dm_contact else "UNKNOWN",
        meeting_time=journey.scheduled_meeting_time if journey.scheduled_meeting_time else "UNKNOWN",
        sdr_name=journey.sdr_name or "Unknown SDR",
        dimensions_table=dim_table
    )

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=60
        )

        brief_sections = json.loads(response.choices[0].message.content.strip())

        # Generate and save HTML Dashboard
        try:
            html_content = generate_html_brief(journey, score_result, brief_sections)
            save_html_brief(journey.company.name, html_content)
        except Exception as e:
            logger.error(f"Error generating HTML dashboard: {e}")

        logger.info(f"✓ Stage 7 complete: Briefs generated for {journey.company.name}")
        return brief_sections

    except Exception as e:
        logger.error(f"OpenAI error generating brief: {e}")
        return None


def save_brief(company_name: str, brief_sections: Dict[str, str], hubspot_call_id: str, company_id: str) -> bool:
    """Save brief sections to local .md file, update HubSpot company property, and mark as sent in Supabase."""
    try:
        # Build markdown content from sections
        markdown_content = f"# {company_name} Handoff Brief\n\n"
        markdown_content += f"## ICP Fit\n{brief_sections.get('icp_fit', 'N/A')}\n\n"
        markdown_content += f"## Current Process\n{brief_sections.get('current_process', 'N/A')}\n\n"
        markdown_content += f"## Evaluating Tools\n{brief_sections.get('evaluating_tools', 'N/A')}\n\n"
        markdown_content += f"## Pain / Need\n{brief_sections.get('pain_need', 'N/A')}\n\n"
        markdown_content += f"## Recommended Next Steps\n{brief_sections.get('next_steps', 'N/A')}\n"

        # Sanitize company name for filename
        safe_name = company_name.replace("/", "_").replace(" ", "_")
        filename = f"/Users/kaustubhchauhan/ae-handoff-brief-agent/handoffs/{safe_name}_handoff.md"

        with open(filename, "w") as f:
            f.write(markdown_content)

        logger.info(f"✓ Brief saved: {filename}")

        # Update HubSpot company property
        if update_company_property(company_id, "ae_handoff_brief", markdown_content):
            logger.info(f"✓ Updated HubSpot company {company_id} with AE Handoff Brief")
        else:
            logger.warning(f"✗ Failed to update HubSpot company property for {company_id}")

        # Mark as sent in Supabase
        update_handoff_sent(company_id, hubspot_call_id)

        return True

    except Exception as e:
        logger.error(f"Error saving brief: {e}")
        return False
