import logging
import json
import os
from typing import Optional
from openai import OpenAI
from lib.types import CompanyJourney, Contact
from lib.supabase_client import upsert_contact

logger = logging.getLogger(__name__)

DM_DISCOVERY_PROMPT = """You are a sales call analyst. Analyze the following cleaned call transcripts to identify the Decision Maker (DM).

TASK:
1. Read all transcripts below
2. Identify WHO the DM is (which person/contact speaks with authority to make decisions)
3. Look for cues like:
   - "I'm the owner/GM/manager"
   - "I'll make the call" or "I'll decide"
   - Being addressed as the decision authority
   - Delegating to someone else ("I'll need to check with...")

CONTEXT:
Company: {company_name}
Contacts at company: {contacts_list}

TRANSCRIPTS:
{transcripts}

OUTPUT: Return ONLY a valid JSON object with these fields:
{{
  "dm_name": "Name of the DM as mentioned in transcripts, or null if unknown",
  "dm_role": "Their role/title as mentioned in conversations, or null",
  "is_decision_maker": true/false,
  "confidence": "high/medium/low",
  "evidence_quote": "Direct quote showing decision-making authority, or null"
}}
"""

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)

def discover_dm(journey: CompanyJourney, cleaned_calls_list: list) -> Optional[Contact]:
    """
    Stage 4.5: DM Discovery from Transcripts
    Analyzes cleaned transcripts to identify the actual decision-maker.
    Returns updated journey.dm_contact or None if not found.
    """
    logger.info(f"→ Stage 4.5: DM Discovery Agent for {journey.company.name}")

    if not journey.contacts:
        logger.warning("  No contacts found, skipping DM discovery")
        return None

    if not cleaned_calls_list:
        logger.warning("  No cleaned transcripts available, skipping DM discovery")
        return None

    try:
        # Concatenate all cleaned transcripts
        transcripts = "\n---\n".join([call.cleaned_transcript for call in cleaned_calls_list if call.cleaned_transcript])

        if not transcripts:
            logger.warning("  No transcript content found, skipping DM discovery")
            return None

        # Build contacts list for context
        contacts_str = "; ".join([f"{c.name} ({c.title})" for c in journey.contacts if c.name])

        # Format prompt
        prompt = DM_DISCOVERY_PROMPT.format(
            company_name=journey.company.name,
            contacts_list=contacts_str,
            transcripts=transcripts
        )

        # Call OpenAI
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=60
        )

        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)

        logger.debug(f"  DM Discovery result: {result}")

        # Match back to contacts by name
        dm_name = result.get("dm_name")
        is_dm = result.get("is_decision_maker", False)
        confidence = result.get("confidence", "low")

        if is_dm and dm_name and confidence in ["high", "medium"]:
            # Fuzzy match to existing contact
            matched_contact = None
            for contact in journey.contacts:
                if contact.name and dm_name.lower() in contact.name.lower():
                    matched_contact = contact
                    break

            if matched_contact:
                matched_contact.is_dm = True
                journey.dm_contact = matched_contact

                # Update contact in Supabase (is_dm will be omitted if column doesn't exist yet)
                upsert_contact({
                    "hubspot_contact_id": matched_contact.hubspot_id,
                    "hubspot_company_id": journey.company.hubspot_id,
                    "name": matched_contact.name,
                    "title": matched_contact.title,
                    "email": matched_contact.email,
                    "is_dm": True
                })

                logger.info(f"  ✓ DM identified: {matched_contact.name} ({matched_contact.title})")
                return matched_contact
            else:
                logger.warning(f"  Could not match DM '{dm_name}' to any contact")
        else:
            logger.warning(f"  No clear DM found (confidence: {confidence})")

        # Fallback to first contact if DM discovery fails
        if not journey.dm_contact and journey.contacts:
            journey.dm_contact = journey.contacts[0]
            logger.info(f"  Using fallback DM: {journey.dm_contact.name}")

        return journey.dm_contact

    except Exception as e:
        logger.error(f"Error in DM discovery: {e}")
        # Fallback to first contact
        if not journey.dm_contact and journey.contacts:
            journey.dm_contact = journey.contacts[0]
        return journey.dm_contact
