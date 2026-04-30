import os
import logging
import requests
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
        props = data.get("properties", {})
        
        # Map disposition ID to label
        disp_id = props.get("hs_call_disposition")
        mapping = get_disposition_mapping()
        disp_label = mapping.get(disp_id) if disp_id else None

        return {
            "hubspot_call_id": call_id,
            "hubspot_company_id": company_id,
            "call_date": props.get("hs_timestamp"),
            "call_disposition_label": disp_label,
            "recording_url": props.get("hs_call_recording_url"),
            "owner_name": get_owner_name(props.get("hubspot_owner_id")) if props.get("hubspot_owner_id") else None
        }
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
