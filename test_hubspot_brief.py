#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from lib.hubspot_client import update_company_property

load_dotenv()

company_id = "80281756374"
test_brief = """# Test Handoff Brief for HubSpot Integration

## ICP Fit
Testing the HubSpot integration with West Mitsubishi.

## Current Process
This is a direct test of the save_brief HubSpot update function.

## Evaluating Tools
Verifying the update_company_property function works.

## Pain / Need
Testing that briefs can be successfully written to HubSpot.

## Recommended Next Steps
This confirms the feature is working end-to-end.
"""

print(f"Testing HubSpot integration...")
print(f"Company ID: {company_id}")
print(f"Brief length: {len(test_brief)} characters")

result = update_company_property(company_id, "ae_handoff_brief", test_brief)

if result:
    print("\n✓ SUCCESS: HubSpot integration is working!")
    print("  Brief was successfully written to the company property")
else:
    print("\n✗ FAILED: Brief was not written to HubSpot")
