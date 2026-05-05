#!/usr/bin/env python3
from dotenv import load_dotenv
from lib.supabase_client import get_supabase

load_dotenv()
supabase = get_supabase()
response = supabase.table("calls").select("hubspot_call_id,hubspot_company_id").eq("ae_brief_sent", False).execute()
print(f"Total pending: {len(response.data)}")
for call in response.data[:6]:
    print(f"  - Call {call['hubspot_call_id']} (Company: {call['hubspot_company_id']})")
