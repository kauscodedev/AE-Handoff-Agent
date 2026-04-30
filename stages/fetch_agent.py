import logging
from typing import Optional, List, Dict, Any
from lib.hubspot_client import get_company, get_company_contacts, get_company_calls, get_call_details
from lib.supabase_client import upsert_call, upsert_contact
from lib.types import Company, Contact, Call, CompanyJourney

logger = logging.getLogger(__name__)

def fetch_company_journey(company_id: str, trigger_call_id: str) -> Optional[CompanyJourney]:
    """
    Stage 2: Fetch Agent
    Pulls all historical calls for a company to build the full journey.
    """
    logger.info(f"→ Stage 2: Fetch Agent for company {company_id}")

    try:
        # 1. Fetch Company Info
        company = get_company(company_id)
        if not company:
            logger.error(f"✗ Could not fetch company {company_id}")
            return None

        # 2. Fetch Contacts
        contacts = get_company_contacts(company_id)
        logger.info(f"  ✓ Found {len(contacts)} contacts")

        # 3. Fetch All Associated Call IDs
        call_ids = get_company_calls(company_id)
        logger.info(f"  ✓ Found {len(call_ids)} calls associated in HubSpot")

        # 4. Fetch Details for Connected Calls
        calls_data = []
        for call_id in call_ids:
            details = get_call_details(call_id, company_id=company_id)
            if details:
                # Filter for Connected Calls only
                disp = details.get("call_disposition_label")
                if disp and (disp.startswith("C - ") or disp == "Connected"):
                    calls_data.append(details)
                    
                    # Sync to Supabase (only send supported columns)
                    db_payload = {
                        "hubspot_call_id": details["hubspot_call_id"],
                        "hubspot_company_id": details["hubspot_company_id"],
                        "call_date": details["call_date"],
                        "call_disposition_label": details["call_disposition_label"],
                        "recording_url": details["recording_url"]
                    }
                    upsert_call(db_payload)
                else:
                    logger.debug(f"    - Skipping non-connected call {call_id} ({disp})")

        if not calls_data:
            logger.warning(f"  No connected calls found for {company_id}")
            return None

        logger.info(f"✓ Stage 2 complete: {company.name} with {len(calls_data)} connected calls tracked")

        # 5. Build Journey Object
        journey = CompanyJourney(company, calls_data)
        journey.contacts = contacts

        # Persist contacts to Supabase
        for contact in contacts:
            contact_data = {
                "hubspot_contact_id": contact.hubspot_id,
                "hubspot_company_id": company_id,
                "name": contact.name,
                "title": contact.title,
                "email": contact.email,
                "is_dm": False  # Will be set by Stage 4.5 (dm_discovery)
            }
            upsert_contact(contact_data)

        # DM identification will be done in Stage 4.5 (dm_discovery) using transcripts
        # For now, set placeholder
        journey.dm_contact = contacts[0] if contacts else None

        # Identify SDR and Meeting Time from most recent call
        sorted_calls = sorted(calls_data, key=lambda x: x.get("call_date", ""), reverse=True)
        if sorted_calls:
            latest = sorted_calls[0]
            journey.sdr_name = latest.get("owner_name")
            journey.scheduled_meeting_time = latest.get("call_date")

        return journey

    except Exception as e:
        logger.error(f"Error fetching journey for {company_id}: {e}")
        return None
