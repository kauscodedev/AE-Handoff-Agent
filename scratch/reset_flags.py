import logging
from dotenv import load_dotenv
from lib.supabase_client import get_supabase

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_handoff_flags():
    try:
        supabase = get_supabase()
        # Reset all ae_brief_sent flags to False
        response = supabase.table("calls").update({"ae_brief_sent": False}).eq("ae_brief_sent", True).execute()
        logger.info(f"✓ Reset {len(response.data)} handoff flags.")
    except Exception as e:
        logger.error(f"Error resetting flags: {e}")

if __name__ == "__main__":
    reset_handoff_flags()
