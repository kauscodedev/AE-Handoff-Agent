import logging
from lib.supabase_client import get_meeting_scheduled_calls

logger = logging.getLogger(__name__)

def watch_for_meeting_scheduled(limit: int = 10) -> list:
    """
    Stage 1: HubSpot Watcher
    Polls HubSpot for calls where `hs_call_disposition` = "C - Meeting Scheduled"
    AND `ae_brief_sent = False`

    Returns: List of pending calls to process
    """
    try:
        calls = get_meeting_scheduled_calls(limit=limit)
        if calls:
            logger.info(f"✓ Watcher found {len(calls)} pending Meeting Scheduled calls")
        else:
            logger.debug("No pending Meeting Scheduled calls found")
        return calls
    except Exception as e:
        logger.error(f"✗ Watcher error: {e}")
        return []
