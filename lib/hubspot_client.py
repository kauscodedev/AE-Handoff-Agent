import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from .types import Company, Contact

logger = logging.getLogger(__name__)

HUBSPOT_API_URL = "https://api.hubapi.com"

def get_headers():
    token = os.getenv("HUBSPOT_TOKEN")
    if not token:
        raise ValueError("HUBSPOT_TOKEN not set")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

# Cache for disposition mappings
_DISPOSITION_MAPPING = None

def get_disposition_mapping() -> Dict[str, str]:
    """Fetch and cache call disposition mappings from HubSpot."""
    global _DISPOSITION_MAPPING
    if _DISPOSITION_MAPPING is not None:
        return _DISPOSITION_MAPPING
    
    try:
        url = f"{HUBSPOT_API_URL}/calling/v1/dispositions"
        response = requests.get(url, headers=get_headers())
        response.raise_for_status()
        options = response.json()
        _DISPOSITION_MAPPING = {opt["id"]: opt["label"] for opt in options}
        return _DISPOSITION_MAPPING
    except Exception as e:
        logger.warning(f"Could not fetch disposition mapping: {e}")
        return {}

def get_disposition_id_by_label(label: str) -> Optional[str]:
    """Find a HubSpot call disposition ID by its display label."""
    mapping = get_disposition_mapping()
    for disposition_id, disposition_label in mapping.items():
        if disposition_label == label:
            return disposition_id
    return None

def get_call_company_id(call_id: str) -> Optional[str]:
    """Fetch the first company associated with a HubSpot call."""
    try:
        url = f"{HUBSPOT_API_URL}/crm/v3/objects/calls/{call_id}/associations/companies"
        response = requests.get(url, headers=get_headers())
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            return None
        return results[0].get("id")
    except Exception as e:
        logger.error(f"Error fetching company association for call {call_id}: {e}")
        return None

def _format_call_details(call_id: str, props: Dict[str, Any], company_id: Optional[str] = None) -> Dict[str, Any]:
    """Normalize HubSpot call properties into the pipeline's call shape."""
    disp_id = props.get("hs_call_disposition")
    mapping = get_disposition_mapping()
    disp_label = mapping.get(disp_id) if disp_id else None
    owner_id = props.get("hubspot_owner_id")
    owner_name = get_owner_name(owner_id) if owner_id else None

    return {
        "hubspot_call_id": call_id,
        "hubspot_company_id": company_id,
        "call_date": props.get("hs_timestamp"),
        "activity_date": props.get("hs_timestamp"),
        "assigned_to": owner_name,
        "owner_name": owner_name,
        "call_outcome": disp_label,
        "call_disposition_label": disp_label,
        "recording_url": props.get("hs_call_recording_url"),
    }

def search_meeting_scheduled_calls(limit: int = 10, days_back: int = 1) -> List[Dict[str, Any]]:
    """
    Search HubSpot calls directly for recent "C - Meeting Scheduled" outcomes.

    Returns call records with activity date, assigned owner, outcome, recording URL,
    and associated company ID so the orchestrator can hand off to Stage 2.
    """
    disposition_id = get_disposition_id_by_label("C - Meeting Scheduled")
    if not disposition_id:
        logger.error("Could not find HubSpot disposition ID for 'C - Meeting Scheduled'")
        return []

    try:
        since = (datetime.now() - timedelta(days=days_back)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        since_ms = int(since.timestamp() * 1000)
        url = f"{HUBSPOT_API_URL}/crm/v3/objects/calls/search"
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "hs_call_disposition",
                            "operator": "EQ",
                            "value": disposition_id,
                        },
                        {
                            "propertyName": "hs_timestamp",
                            "operator": "GTE",
                            "value": str(since_ms),
                        },
                    ]
                }
            ],
            "properties": [
                "hs_timestamp",
                "hubspot_owner_id",
                "hs_call_title",
                "hs_call_disposition",
                "hs_call_recording_url",
            ],
            "sorts": [
                {
                    "propertyName": "hs_timestamp",
                    "direction": "DESCENDING",
                }
            ],
            "limit": min(limit, 100),
        }
        response = requests.post(url, headers=get_headers(), json=payload)
        response.raise_for_status()

        calls = []
        for item in response.json().get("results", []):
            call_id = item.get("id")
            if not call_id:
                continue

            company_id = get_call_company_id(call_id)
            if not company_id:
                logger.warning(f"Skipping Meeting Scheduled call {call_id}: no associated company")
                continue

            calls.append(_format_call_details(call_id, item.get("properties", {}), company_id))

        return calls
    except Exception as e:
        logger.error(f"Error searching HubSpot Meeting Scheduled calls: {e}")
        return []

def get_company(company_id: str) -> Optional[Company]:
    """Fetch company details from HubSpot."""
    try:
        url = f"{HUBSPOT_API_URL}/crm/v3/objects/companies/{company_id}"
        params = {
            "properties": ["name", "numberofemployees", "country"]
        }
        response = requests.get(url, headers=get_headers(), params=params)
        response.raise_for_status()
        data = response.json()
        props = data.get("properties", {})
        return Company(
            hubspot_id=company_id,
            name=props.get("name") or "Unknown",
            employees=int(props.get("numberofemployees")) if props.get("numberofemployees") else None,
            location=props.get("country")
        )
    except Exception as e:
        logger.error(f"Error fetching company {company_id}: {e}")
        return None

def get_company_contacts(company_id: str) -> List[Contact]:
    """Fetch all contacts associated with a company."""
    try:
        url = f"{HUBSPOT_API_URL}/crm/v3/objects/companies/{company_id}/associations/contacts"
        response = requests.get(url, headers=get_headers())
        response.raise_for_status()
        data = response.json()
        contact_ids = [assoc["id"] for assoc in data.get("results", [])]

        contacts = []
        for contact_id in contact_ids:
            contact = get_contact(contact_id)
            if contact:
                contacts.append(contact)
        return contacts
    except Exception as e:
        logger.error(f"Error fetching contacts for company {company_id}: {e}")
        return []

def get_contact(contact_id: str) -> Optional[Contact]:
    """Fetch contact details from HubSpot."""
    try:
        url = f"{HUBSPOT_API_URL}/crm/v3/objects/contacts/{contact_id}"
        params = {
            "properties": ["firstname", "lastname", "jobtitle", "email"]
        }
        response = requests.get(url, headers=get_headers(), params=params)
        response.raise_for_status()
        data = response.json()
        props = data.get("properties", {})
        first_name = props.get("firstname") or ""
        last_name = props.get("lastname") or ""
        name = f"{first_name} {last_name}".strip()
        return Contact(
            hubspot_id=contact_id,
            name=name or "Unknown",
            title=props.get("jobtitle"),
            email=props.get("email")
        )
    except Exception as e:
        logger.error(f"Error fetching contact {contact_id}: {e}")
        return None

def get_company_calls(company_id: str) -> List[str]:
    """Fetch all call IDs associated with a company."""
    try:
        url = f"{HUBSPOT_API_URL}/crm/v3/objects/companies/{company_id}/associations/calls"
        response = requests.get(url, headers=get_headers())
        response.raise_for_status()
        data = response.json()
        call_ids = [assoc["id"] for assoc in data.get("results", [])]
        return call_ids
    except Exception as e:
        logger.error(f"Error fetching calls for company {company_id}: {e}")
        return []

def get_call_details(call_id: str, company_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch call details from HubSpot."""
    try:
        url = f"{HUBSPOT_API_URL}/crm/v3/objects/calls/{call_id}"
        params = {
            "properties": ["hs_timestamp", "hubspot_owner_id", "hs_call_title", "hs_call_disposition", "hs_call_recording_url"]
        }
        response = requests.get(url, headers=get_headers(), params=params)
        response.raise_for_status()
        data = response.json()
        return _format_call_details(call_id, data.get("properties", {}), company_id)
    except Exception as e:
        logger.error(f"Error fetching call {call_id}: {e}")
        return None

def get_owner_name(owner_id: str) -> Optional[str]:
    """Fetch owner/SDR name from HubSpot Owners API."""
    if not owner_id:
        return None
    try:
        url = f"{HUBSPOT_API_URL}/crm/v3/owners/{owner_id}"
        response = requests.get(url, headers=get_headers())
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        first_name = data.get("firstName") or ""
        last_name = data.get("lastName") or ""
        return f"{first_name} {last_name}".strip() or None
    except Exception as e:
        logger.debug(f"Could not fetch owner name for {owner_id}: {e}")
        return None
