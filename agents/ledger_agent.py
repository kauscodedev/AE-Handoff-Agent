import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Set

from lib.supabase_client import get_supabase, update_ae_handoff_run, upsert_ae_handoff_run

from .contracts import TriggerCandidate

logger = logging.getLogger(__name__)


TERMINAL_SUCCESS = {"completed"}
ACTIVE_STATUSES = {"discovered", "processing"}
STALE_RUN_AFTER_MINUTES = int(os.getenv("AE_HANDOFF_STALE_RUN_MINUTES", "45"))


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

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _parse_timestamp(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def is_stale_active_run(self, run: Optional[Dict]) -> bool:
        if not run or run.get("status") not in ACTIVE_STATUSES:
            return False

        heartbeat_at = self._parse_timestamp(run.get("updated_at")) or self._parse_timestamp(run.get("created_at"))
        if not heartbeat_at:
            logger.warning(
                "Ledger treating active trigger %s as stale because it has no timestamp",
                run.get("trigger_call_id"),
            )
            return True

        age = datetime.now(timezone.utc) - heartbeat_at
        is_stale = age > timedelta(minutes=STALE_RUN_AFTER_MINUTES)
        if is_stale:
            logger.warning(
                "Ledger treating active trigger %s as stale: status=%s age=%ss threshold=%sm",
                run.get("trigger_call_id"),
                run.get("status"),
                int(age.total_seconds()),
                STALE_RUN_AFTER_MINUTES,
            )
        return is_stale

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
            return self.is_stale_active_run(run)
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
        if existing and existing.get("status") in ACTIVE_STATUSES and not self.is_stale_active_run(existing):
            logger.info(f"Ledger skip: trigger {trigger.hubspot_call_id} is already {existing.get('status')}")
            return None

        now = self._now()
        if existing and self.is_stale_active_run(existing):
            logger.warning(f"Ledger reclaiming stale trigger {trigger.hubspot_call_id}")

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
                "completed_at": None,
                "updated_at": now,
                "metadata": {
                    "heartbeat_stage": "claimed",
                    "heartbeat_at": now,
                    "stale_reclaim": bool(existing and self.is_stale_active_run(existing)),
                },
            }
        )
        if run_id:
            logger.info(f"Ledger claimed trigger {trigger.hubspot_call_id} as run {run_id}")
        return run_id

    def complete(self, run_id: Optional[str]) -> None:
        if run_id:
            now = self._now()
            update_ae_handoff_run(
                run_id,
                {
                    "status": "completed",
                    "completed_at": now,
                    "error_message": None,
                    "updated_at": now,
                },
            )

    def fail(self, run_id: Optional[str], message: str) -> None:
        if run_id:
            now = self._now()
            update_ae_handoff_run(
                run_id,
                {
                    "status": "failed",
                    "error_message": message,
                    "completed_at": now,
                    "updated_at": now,
                },
            )

    def heartbeat(self, run_id: Optional[str], stage: str) -> None:
        if not run_id:
            return
        now = self._now()
        update_ae_handoff_run(
            run_id,
            {
                "updated_at": now,
                "metadata": {
                    "heartbeat_stage": stage,
                    "heartbeat_at": now,
                },
            },
        )
