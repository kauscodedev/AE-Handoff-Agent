import logging
from datetime import datetime, timedelta, timezone
from typing import List

from lib.hubspot_client import search_meeting_scheduled_calls

from .contracts import TriggerCandidate
from .ledger_agent import RunLedgerAgent

logger = logging.getLogger(__name__)


class TriggerDiscoveryAgent:
    """
    Reconciles HubSpot triggers against the durable run ledger.

    It intentionally scans a rolling lookback window rather than trusting a
    strict cursor, because HubSpot call activity timestamps can be older than
    the time the record becomes visible or corrected.
    """

    def __init__(self, ledger: RunLedgerAgent, lookback_hours: int = 48, limit: int = 100):
        self.ledger = ledger
        self.lookback_hours = lookback_hours
        self.limit = limit

    def discover(self) -> List[TriggerCandidate]:
        since = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)
        since_ms = int(since.timestamp() * 1000)
        raw_calls = search_meeting_scheduled_calls(limit=self.limit, since_timestamp_ms=since_ms)
        triggers = [TriggerCandidate.from_hubspot(item) for item in raw_calls]
        completed_ids = self.ledger.completed_trigger_ids(item.hubspot_call_id for item in triggers)
        pending = [
            item
            for item in triggers
            if item.hubspot_call_id not in completed_ids and self.ledger.should_process(item)
        ]

        logger.info(
            "Discovery reconciled %s HubSpot Meeting Scheduled calls over %sh; %s need work",
            len(triggers),
            self.lookback_hours,
            len(pending),
        )
        return pending

