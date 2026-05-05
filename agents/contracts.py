from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TriggerCandidate:
    """A HubSpot Meeting Scheduled call that may need a handoff run."""

    hubspot_call_id: str
    hubspot_company_id: str
    activity_date: Optional[str]
    assigned_to: Optional[str]
    call_outcome: Optional[str]
    recording_url: Optional[str]
    raw: Dict[str, Any]

    @classmethod
    def from_hubspot(cls, data: Dict[str, Any]) -> "TriggerCandidate":
        return cls(
            hubspot_call_id=str(data["hubspot_call_id"]),
            hubspot_company_id=str(data.get("hubspot_company_id") or "INDIVIDUAL"),
            activity_date=data.get("activity_date") or data.get("call_date"),
            assigned_to=data.get("assigned_to") or data.get("owner_name"),
            call_outcome=data.get("call_outcome") or data.get("call_disposition_label"),
            recording_url=data.get("recording_url"),
            raw=data,
        )


@dataclass(frozen=True)
class AgentResult:
    """Standard result shape for coordinator-visible sub-agent work."""

    ok: bool
    message: str
    data: Optional[Dict[str, Any]] = None

