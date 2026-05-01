import logging
from lib.hubspot_client import search_meeting_scheduled_calls
from lib.supabase_client import get_sent_handoff_call_ids

logger = logging.getLogger(__name__)

def watch_for_meeting_scheduled(limit: int = 10) -> list:
    """
    Stage 1: HubSpot Watcher
    Polls HubSpot directly for calls where `hs_call_disposition` = "C - Meeting Scheduled",
    then skips calls already marked `ae_brief_sent = True` in Supabase.

    Returns: List of pending calls to process
    """
    try:
        calls = search_meeting_scheduled_calls(limit=limit)
        sent_call_ids = get_sent_handoff_call_ids([call["hubspot_call_id"] for call in calls])
        pending_calls = [
            call for call in calls
            if call["hubspot_call_id"] not in sent_call_ids
        ]

        if pending_calls:
            logger.info(f"✓ Watcher found {len(pending_calls)} pending Meeting Scheduled calls in HubSpot")
        else:
            logger.debug("No pending Meeting Scheduled calls found")
        return pending_calls
    except Exception as e:
        logger.error(f"✗ Watcher error: {e}")
        return []
