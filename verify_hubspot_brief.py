#!/usr/bin/env python3
import os
import requests
from dotenv import load_dotenv

load_dotenv()

company_id = "80281756374"
token = os.getenv("HUBSPOT_TOKEN")
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}

url = f"https://api.hubapi.com/crm/v3/objects/companies/{company_id}"
params = {"properties": ["ae_handoff_brief"]}

print(f"Verifying brief was saved to HubSpot company {company_id}...")
response = requests.get(url, headers=headers, params=params)

if response.status_code == 200:
    data = response.json()
    brief_content = data.get("properties", {}).get("ae_handoff_brief")

    if brief_content:
        print("✓ VERIFIED: Brief is stored in HubSpot property 'ae_handoff_brief'")
        print(f"\nBrief content preview (first 300 chars):")
        print(f"{brief_content[:300]}...\n")
        print(f"Total length: {len(brief_content)} characters")
    else:
        print("✗ Property not found or is empty in HubSpot")
else:
    print(f"✗ HubSpot API error: {response.status_code}")
    print(response.text)
