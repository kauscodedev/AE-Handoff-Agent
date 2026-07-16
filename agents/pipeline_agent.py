import logging
from typing import Callable

from .contracts import AgentResult, TriggerCandidate

logger = logging.getLogger(__name__)


class HandoffPipelineAgent:
    """
    Executes the specialist sub-agent chain for one claimed trigger.

    The current specialists are the existing stage modules: context fetch,
    transcription, transcript cleaning, DM discovery, BANTIC analysis,
    deterministic scoring, and brief generation.
    """

    def __init__(self, process_trigger: Callable[[str, str], bool]):
        self.process_trigger = process_trigger

    def run(self, trigger: TriggerCandidate) -> AgentResult:
        logger.info(
            "PipelineAgent starting trigger=%s company=%s owner=%s",
            trigger.hubspot_call_id,
            trigger.hubspot_company_id,
            trigger.assigned_to,
        )
        ok = self.process_trigger(trigger.hubspot_company_id, trigger.hubspot_call_id)
        if ok:
            return AgentResult(True, "handoff completed", {"trigger_call_id": trigger.hubspot_call_id})
        return AgentResult(False, "handoff pipeline returned false", {"trigger_call_id": trigger.hubspot_call_id})

