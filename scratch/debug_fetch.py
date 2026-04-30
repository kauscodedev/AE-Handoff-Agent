
import os
import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from lib.supabase_client import get_supabase
from stages.fetch_agent import fetch_company_journey

load_dotenv()

def debug_fetch_since_yesterday():
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_iso = yesterday.isoformat().replace("+00:00", "Z")
    
    print(f"Searching for calls since: {yesterday_iso}")
    
    supabase = get_supabase()
    response = supabase.table("calls").select(
        "hubspot_call_id, hubspot_company_id, call_date, call_disposition_label"
    ).eq("call_disposition_label", "C - Meeting Scheduled").gte("call_date", yesterday_iso).order("call_date", desc=True).execute()
    
    calls = response.data
    print(f"Found {len(calls)} calls in DB since yesterday.")
    
    for call in calls:
        call_id = call["hubspot_call_id"]
        company_id = call["hubspot_company_id"]
        print(f"\n--- Fetching for Call {call_id} (Company {company_id}) ---")
        
        journey = fetch_company_journey(call_id, company_id)
        if journey:
            print(f"Company: {journey.company.name} ({journey.company.location}, {journey.company.employees} employees)")
            print(f"Contacts: {len(journey.contacts)}")
            for c in journey.contacts[:3]:
                print(f"  - {c.name} ({c.title})")
            
            print(f"Calls in Journey: {len(journey.calls)}")
            for i, c_data in enumerate(journey.calls[:3]):
                print(f"  Call {i+1}: {c_data['hubspot_call_id']} | Date: {c_data['call_date']} | Status: {c_data.get('analysis_status')}")
                # Check if it has BANTIC scores
                scores = {k: v for k, v in c_data.items() if k.startswith("score_")}
                if scores:
                    print(f"    Scores: {scores}")
                else:
                    print(f"    No scores found in DB record.")
        else:
            print(f"Failed to fetch journey for {company_id}")

if __name__ == "__main__":
    debug_fetch_since_yesterday()
