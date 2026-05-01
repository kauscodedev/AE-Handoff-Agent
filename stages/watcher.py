import logging
import json
from pathlib import Path
from datetime import datetime, timezone
from lib.hubspot_client import search_meeting_scheduled_calls
from lib.supabase_client import get_sent_handoff_call_ids

logger = logging.getLogger(__name__)
WATCHER_STATE_FILE = Path(".watcher_state.json")

def _load_last_watcher_run_ms() -> int:
    """Load the last watcher run timestamp (ms) or return 0 if not found."""
    if not WATCHER_STATE_FILE.exists():
        return 0
    try:
        state = json.loads(WATCHER_STATE_FILE.read_text())
        return state.get("last_run_timestamp_ms", 0)
    except Exception as e:
        logger.warning(f"Could not load watcher state: {e}, starting fresh")
        return 0

def _save_last_watcher_run_ms(timestamp_ms: int):
    """Save the current watcher run timestamp (ms) to state file."""
    try:
        state = {
            "last_run_timestamp_ms": timestamp_ms,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        WATCHER_STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.error(f"Could not save watcher state: {e}")

def watch_for_meeting_scheduled(limit: int = 10) -> list:
    """
    Stage 1: HubSpot Watcher
    Polls HubSpot directly for calls where `hs_call_disposition` = "C - Meeting Scheduled",
    only fetching calls created AFTER the last successful watcher run.
    Then skips calls already marked `ae_brief_sent = True` in Supabase.

    Returns: List of pending calls to process
    """
    try:
        last_run_ms = _load_last_watcher_run_ms()
        current_run_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        calls = search_meeting_scheduled_calls(limit=limit, since_timestamp_ms=last_run_ms if last_run_ms > 0 else None)
        sent_call_ids = get_sent_handoff_call_ids([call["hubspot_call_id"] for call in calls])
        pending_calls = [
            call for call in calls
            if call["hubspot_call_id"] not in sent_call_ids
        ]

        if pending_calls:
            logger.info(f"✓ Watcher found {len(pending_calls)} NEW Meeting Scheduled calls in HubSpot since last run")
        else:
            logger.debug("No new Meeting Scheduled calls found since last run")

        # Update watcher state with current timestamp for next run
        _save_last_watcher_run_ms(current_run_ms)

        return pending_calls
    except Exception as e:
        logger.error(f"✗ Watcher error: {e}")
        return []
