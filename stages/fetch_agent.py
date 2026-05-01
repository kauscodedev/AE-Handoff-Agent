import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from lib.hubspot_client import get_company, get_company_contacts, get_company_calls, get_call_details
from lib.supabase_client import get_calls_for_company, upsert_call
from lib.types import Company, Contact, Call, CompanyJourney

logger = logging.getLogger(__name__)

ALLOWED_ANALYSIS_DISPOSITIONS = {
    "cmeetingscheduled",
    "ccallbackhighintent",
    "ccallbacklowintent",
    "cgaveareferral",
    "connected",
}

def _normalize_disposition(label: Optional[str]) -> str:
    if not label:
        return ""
    return "".join(ch.lower() for ch in label if ch.isalnum())

def _parse_call_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value)
    if text.isdigit():
        return datetime.fromtimestamp(int(text) / 1000)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

def fetch_company_journey(company_id: str, trigger_call_id: str) -> Optional[CompanyJourney]:
    """
    Stage 2: Fetch Agent
    Pulls all historical calls for a company to build the full journey.
    """
    logger.info(f"→ Stage 2: Fetch Agent for company {company_id}")

    try:
        if not company_id or company_id == "INDIVIDUAL":
            trigger_call = get_call_details(trigger_call_id, company_id="INDIVIDUAL")
            if not trigger_call:
                logger.error(f"✗ Could not fetch trigger call {trigger_call_id} for individual prospect flow")
                return None

            call_date = _parse_call_date(trigger_call.get("call_date"))
            company = Company(
                hubspot_id="INDIVIDUAL",
                name="Individual Prospect",
                employees=None,
                location=None,
            )

            merged = {
                **trigger_call,
                "call_outcome": trigger_call.get("call_outcome") or trigger_call.get("call_disposition_label"),
                "assigned_to": trigger_call.get("assigned_to") or trigger_call.get("owner_name"),
                "is_trigger_call": True,
            }

            upsert_call({
                "hubspot_call_id": trigger_call["hubspot_call_id"],
                "hubspot_company_id": "INDIVIDUAL",
                "call_date": trigger_call["call_date"],
                "call_disposition_label": trigger_call["call_disposition_label"],
                "recording_url": trigger_call["recording_url"],
            })

            journey = CompanyJourney(company, [merged])
            journey.contacts = []
            journey.dm_contact = None
            journey.sdr_name = trigger_call.get("owner_name")
            journey.scheduled_meeting_time = call_date or trigger_call.get("call_date")

            logger.info("✓ Stage 2 complete: individual prospect flow with trigger call only")
            return journey

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

        existing_calls = {
            row["hubspot_call_id"]: row
            for row in get_calls_for_company(company_id)
        }

        trigger_call_details = get_call_details(trigger_call_id, company_id=company_id)
        trigger_call_date = _parse_call_date(trigger_call_details.get("call_date")) if trigger_call_details else None

        # 4. Fetch Details for allowed historical analysis calls
        calls_data = []
        for call_id in call_ids:
            details = get_call_details(call_id, company_id=company_id)
            if details:
                normalized = _normalize_disposition(details.get("call_disposition_label"))
                call_date = _parse_call_date(details.get("call_date"))
                is_trigger_call = call_id == trigger_call_id
                is_allowed = normalized in ALLOWED_ANALYSIS_DISPOSITIONS
                is_previous_or_trigger = is_trigger_call or (
                    trigger_call_date is None or call_date is None or call_date <= trigger_call_date
                )

                if is_allowed and is_previous_or_trigger:
                    merged = {
                        **details,
                        **existing_calls.get(call_id, {}),
                        "hubspot_call_id": details["hubspot_call_id"],
                        "hubspot_company_id": details["hubspot_company_id"],
                        "call_date": details["call_date"],
                        "call_disposition_label": details["call_disposition_label"],
                        "call_outcome": details.get("call_outcome") or details["call_disposition_label"],
                        "recording_url": details["recording_url"],
                        "assigned_to": details.get("assigned_to") or details.get("owner_name"),
                        "owner_name": details.get("owner_name"),
                        "is_trigger_call": is_trigger_call,
                    }
                    calls_data.append(merged)

                    # Sync current HubSpot metadata to Supabase
                    db_payload = {
                        "hubspot_call_id": details["hubspot_call_id"],
                        "hubspot_company_id": details["hubspot_company_id"],
                        "call_date": details["call_date"],
                        "call_disposition_label": details["call_disposition_label"],
                        "recording_url": details["recording_url"]
                    }
                    upsert_call(db_payload)
                else:
                    logger.debug(
                        f"    - Skipping call {call_id} ({details.get('call_disposition_label')}) "
                        f"allowed={is_allowed} previous_or_trigger={is_previous_or_trigger}"
                    )

        if not calls_data:
            logger.warning(f"  No connected calls found for {company_id}")
            return None

        logger.info(f"✓ Stage 2 complete: {company.name} with {len(calls_data)} connected calls tracked")

        # 5. Build Journey Object
        journey = CompanyJourney(company, calls_data)
        journey.contacts = contacts

        # HubSpot is the source of truth for contacts.
        journey.dm_contact = contacts[0] if contacts else None

        # Identify SDR and meeting time from the trigger call, not arbitrary call order.
        trigger_call = next((call for call in calls_data if call.get("is_trigger_call")), None)
        if trigger_call:
            journey.sdr_name = trigger_call.get("owner_name")
            journey.scheduled_meeting_time = trigger_call.get("call_date")
        elif calls_data:
            latest = sorted(calls_data, key=lambda x: x.get("call_date", ""), reverse=True)[0]
            journey.sdr_name = latest.get("owner_name")
            journey.scheduled_meeting_time = latest.get("call_date")

        return journey

    except Exception as e:
        logger.error(f"Error fetching journey for {company_id}: {e}")
        return None
