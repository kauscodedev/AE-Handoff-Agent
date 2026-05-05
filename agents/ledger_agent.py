import logging
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional, Set

from lib.supabase_client import get_supabase, update_ae_handoff_run, upsert_ae_handoff_run

from .contracts import TriggerCandidate

logger = logging.getLogger(__name__)


TERMINAL_SUCCESS = {"completed"}
ACTIVE_STATUSES = {"discovered", "processing"}


class RunLedgerAgent:
    """
    Durable trigger ledger backed by ae_handoff_runs.

    This is the idempotency source of truth. The legacy calls.ae_brief_sent flag
    remains a compatibility marker and transcript cache helper, but the
    coordinator decides whether to process a trigger from ae_handoff_runs.
    """

    def get_run(self, trigger_call_id: str) -> Optional[Dict]:
        try:
            response = (
                get_supabase()
                .table("ae_handoff_runs")
                .select("*")
                .eq("trigger_call_id", trigger_call_id)
                .limit(1)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Ledger read failed for trigger {trigger_call_id}: {e}")
            return None

    def completed_trigger_ids(self, trigger_call_ids: Iterable[str]) -> Set[str]:
        ids = [str(item) for item in trigger_call_ids if item]
        if not ids:
            return set()
        try:
            response = (
                get_supabase()
                .table("ae_handoff_runs")
                .select("trigger_call_id")
                .in_("trigger_call_id", ids)
                .eq("status", "completed")
                .execute()
            )
            return {str(row["trigger_call_id"]) for row in response.data}
        except Exception as e:
            logger.error(f"Ledger completed-trigger lookup failed: {e}")
            return set()

    def should_process(self, trigger: TriggerCandidate, retry_failed: bool = True) -> bool:
        run = self.get_run(trigger.hubspot_call_id)
        if not run:
            return True

        status = run.get("status")
        if status in TERMINAL_SUCCESS:
            return False
        if status in ACTIVE_STATUSES:
            return False
        if status == "failed":
            return retry_failed
        return True

    def claim(self, trigger: TriggerCandidate) -> Optional[str]:
        """
        Create or update a run as processing unless it has already completed.
        Returns the run id when the trigger is claimed.
        """
        existing = self.get_run(trigger.hubspot_call_id)
        if existing and existing.get("status") in TERMINAL_SUCCESS:
            logger.info(f"Ledger skip: trigger {trigger.hubspot_call_id} is already completed")
            return None
        if existing and existing.get("status") in ACTIVE_STATUSES:
            logger.info(f"Ledger skip: trigger {trigger.hubspot_call_id} is already {existing.get('status')}")
            return None

        run_id = upsert_ae_handoff_run(
            {
                "status": "processing",
                "trigger_call_id": trigger.hubspot_call_id,
                "trigger_call_outcome": trigger.call_outcome,
                "trigger_assigned_to": trigger.assigned_to,
                "trigger_activity_date": trigger.activity_date,
                "trigger_recording_url": trigger.recording_url,
                "hubspot_company_id": trigger.hubspot_company_id,
                "error_message": None,
            }
        )
        if run_id:
            logger.info(f"Ledger claimed trigger {trigger.hubspot_call_id} as run {run_id}")
        return run_id

    def complete(self, run_id: Optional[str]) -> None:
        if run_id:
            update_ae_handoff_run(
                run_id,
                {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error_message": None,
                },
            )

    def fail(self, run_id: Optional[str], message: str) -> None:
        if run_id:
            update_ae_handoff_run(
                run_id,
                {
                    "status": "failed",
                    "error_message": message,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
