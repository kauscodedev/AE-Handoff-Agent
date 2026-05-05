import logging
import time
from datetime import datetime, timezone
from typing import Optional

from .contracts import AgentResult
from .discovery_agent import TriggerDiscoveryAgent
from .ledger_agent import RunLedgerAgent
from .pipeline_agent import HandoffPipelineAgent

logger = logging.getLogger(__name__)


class CoordinatorAgent:
    """
    Top-level agent loop.

    Responsibilities:
    - ask DiscoveryAgent to reconcile HubSpot against the durable run ledger
    - claim one trigger at a time in RunLedgerAgent
    - delegate execution to HandoffPipelineAgent
    - write terminal run state even when a specialist fails
    """

    def __init__(
        self,
        discovery: TriggerDiscoveryAgent,
        ledger: RunLedgerAgent,
        pipeline: HandoffPipelineAgent,
        pause_between_triggers_seconds: int = 2,
    ):
        self.discovery = discovery
        self.ledger = ledger
        self.pipeline = pipeline
        self.pause_between_triggers_seconds = pause_between_triggers_seconds

    def run_once(self) -> AgentResult:
        logger.info("[%s] Coordinator tick", datetime.now(timezone.utc).isoformat())
        triggers = self.discovery.discover()
        if not triggers:
            return AgentResult(True, "no pending triggers", {"processed": 0})

        processed = 0
        failed = 0
        for trigger in triggers:
            run_id: Optional[str] = self.ledger.claim(trigger)
            if not run_id:
                continue

            result = self.pipeline.run(trigger)
            if result.ok:
                self.ledger.complete(run_id)
                processed += 1
            else:
                self.ledger.fail(run_id, result.message)
                failed += 1
            time.sleep(self.pause_between_triggers_seconds)

        ok = failed == 0
        return AgentResult(ok, f"processed={processed} failed={failed}", {"processed": processed, "failed": failed})

