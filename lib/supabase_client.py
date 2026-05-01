import os
import logging
from datetime import datetime, timedelta
from typing import Set
from supabase import create_client

logger = logging.getLogger(__name__)

_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
        _supabase = create_client(url, key)
    return _supabase

def get_calls_for_company(company_id: str) -> list:
    """Fetch all calls for a company from Supabase."""
    try:
        supabase = get_supabase()
        response = supabase.table("calls").select(
            "hubspot_call_id, recording_url, call_date, raw_transcript, cleaned_transcript, "
            "score_budget, score_authority, score_need, score_timeline, score_impact, score_current_process, "
            "budget_evidence, authority_evidence, need_evidence, timeline_evidence, impact_evidence, current_process_evidence, "
            "budget_info_captured, authority_info_captured, need_info_captured, timeline_info_captured, impact_info_captured, current_process_info_captured, "
            "overall_summary, bantic_weighted_score, bantic_qualification_tier, analysis_status"
        ).eq("hubspot_company_id", company_id).order("call_date", desc=True).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error fetching calls for company {company_id}: {e}")
        return []

def update_handoff_sent(company_id: str, hubspot_call_id: str) -> bool:
    """Mark handoff as sent for a company."""
    try:
        supabase = get_supabase()
        supabase.table("calls").update({"ae_brief_sent": True, "ae_brief_generated_at": "now()"}).eq(
            "hubspot_call_id", hubspot_call_id
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating handoff_sent for {hubspot_call_id}: {e}")
        return False

def get_meeting_scheduled_calls(limit: int = 20) -> list:
    """Fetch calls with 'C - Meeting Scheduled' disposition since start of yesterday where handoff not yet sent."""
    try:
        supabase = get_supabase()
        # Start of yesterday
        yesterday = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        
        response = supabase.table("calls").select(
            "hubspot_call_id, hubspot_company_id, call_date"
        ).eq("call_disposition_label", "C - Meeting Scheduled")\
         .eq("ae_brief_sent", False)\
         .gte("call_date", yesterday)\
         .order("call_date", desc=True)\
         .limit(limit).execute()
        
        return response.data
    except Exception as e:
        logger.error(f"Error fetching Meeting Scheduled calls: {e}")
        return []

def get_sent_handoff_call_ids(call_ids: list) -> Set[str]:
    """Return call IDs already marked as handoff sent in Supabase."""
    if not call_ids:
        return set()

    try:
        supabase = get_supabase()
        response = supabase.table("calls").select(
            "hubspot_call_id"
        ).in_("hubspot_call_id", call_ids)\
         .eq("ae_brief_sent", True)\
         .execute()
        return {row["hubspot_call_id"] for row in response.data}
    except Exception as e:
        logger.error(f"Error checking sent handoff call IDs: {e}")
        return set()

def upsert_call(call_data: dict) -> bool:
    """Upsert call data into Supabase."""
    try:
        supabase = get_supabase()
        supabase.table("calls").upsert(call_data, on_conflict="hubspot_call_id").execute()
        return True
    except Exception as e:
        logger.error(f"Error upserting call {call_data.get('hubspot_call_id')}: {e}")
        return False

def update_call_fields(hubspot_call_id: str, fields: dict) -> bool:
    """Update any fields on a call row by call ID."""
    try:
        supabase = get_supabase()
        supabase.table("calls").update(fields).eq("hubspot_call_id", hubspot_call_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating call fields for {hubspot_call_id}: {e}")
        return False

def upsert_contact(contact_data: dict) -> bool:
    """Upsert contact data into Supabase contacts table."""
    try:
        supabase = get_supabase()
        # Remove is_dm if the column doesn't exist yet in the schema
        data_to_upsert = {k: v for k, v in contact_data.items() if k != "is_dm"}
        supabase.table("contacts").upsert(data_to_upsert, on_conflict="hubspot_contact_id").execute()
        # Note: is_dm column should be added to Supabase schema separately
        return True
    except Exception as e:
        logger.error(f"Error upserting contact {contact_data.get('hubspot_contact_id')}: {e}")
        return False

def get_contacts_for_company(company_id: str) -> list:
    """Fetch all contacts for a company from Supabase."""
    try:
        supabase = get_supabase()
        response = supabase.table("contacts").select(
            "hubspot_contact_id, name, title, email"
        ).eq("hubspot_company_id", company_id).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error fetching contacts for company {company_id}: {e}")
        return []

def create_ae_handoff_run(run_data: dict) -> str:
    """Create a new ae_handoff_runs record. Returns run_id on success."""
    try:
        supabase = get_supabase()
        response = supabase.table("ae_handoff_runs").insert(run_data).execute()
        if response.data and len(response.data) > 0:
            return response.data[0].get("id")
        return None
    except Exception as e:
        logger.error(f"Error creating ae_handoff_run: {e}")
        return None

def upsert_ae_handoff_run(run_data: dict) -> str:
    """Upsert an ae_handoff_runs record by trigger_call_id. Returns run_id on success."""
    try:
        supabase = get_supabase()
        response = supabase.table("ae_handoff_runs").upsert(
            run_data,
            on_conflict="trigger_call_id"
        ).execute()
        if response.data and len(response.data) > 0:
            return response.data[0].get("id")
        return None
    except Exception as e:
        logger.error(f"Error upserting ae_handoff_run: {e}")
        return None

def update_ae_handoff_run(run_id: str, updates: dict) -> bool:
    """Update an ae_handoff_runs record."""
    try:
        supabase = get_supabase()
        supabase.table("ae_handoff_runs").update(updates).eq("id", run_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating ae_handoff_run {run_id}: {e}")
        return False

def create_ae_handoff_run_call(call_data: dict) -> bool:
    """Create a new ae_handoff_run_calls record."""
    try:
        supabase = get_supabase()
        supabase.table("ae_handoff_run_calls").insert(call_data).execute()
        return True
    except Exception as e:
        logger.error(f"Error creating ae_handoff_run_call: {e}")
        return False

def upsert_ae_handoff_run_call(call_data: dict) -> str:
    """Upsert an ae_handoff_run_calls record by (run_id, hubspot_call_id). Returns row id on success."""
    try:
        supabase = get_supabase()
        response = supabase.table("ae_handoff_run_calls").upsert(
            call_data,
            on_conflict="run_id,hubspot_call_id"
        ).execute()
        if response.data and len(response.data) > 0:
            return response.data[0].get("id")
        return None
    except Exception as e:
        logger.error(f"Error upserting ae_handoff_run_call: {e}")
        return None

def update_ae_handoff_run_call(call_id: str, updates: dict) -> bool:
    """Update an ae_handoff_run_calls record."""
    try:
        supabase = get_supabase()
        supabase.table("ae_handoff_run_calls").update(updates).eq("id", call_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating ae_handoff_run_call {call_id}: {e}")
        return False

def update_ae_handoff_run_call_by_keys(run_id: str, hubspot_call_id: str, updates: dict) -> bool:
    """Update ae_handoff_run_calls by composite business key."""
    try:
        supabase = get_supabase()
        supabase.table("ae_handoff_run_calls").update(updates).eq("run_id", run_id).eq(
            "hubspot_call_id", hubspot_call_id
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating ae_handoff_run_call for run={run_id} call={hubspot_call_id}: {e}")
        return False
