
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(url, key)

response = supabase.table("calls").select("hubspot_call_id").limit(1).execute()
print(f"Type of response: {type(response)}")
print(f"Response: {response}")

try:
    data, count = response
    print(f"Data: {data}")
    print(f"Count: {count}")
except Exception as e:
    print(f"Failed to unpack: {e}")
