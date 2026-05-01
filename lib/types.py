from typing import Optional, Dict, Any, List
from datetime import datetime

class Company:
    def __init__(self, hubspot_id: str, name: str, employees: Optional[int] = None, location: Optional[str] = None):
        self.hubspot_id = hubspot_id
        self.name = name
        self.employees = employees
        self.location = location

class Contact:
    def __init__(self, hubspot_id: str, name: str, title: Optional[str] = None, email: Optional[str] = None):
        self.hubspot_id = hubspot_id
        self.name = name
        self.title = title
        self.email = email
        self.is_dm = False

class Call:
    def __init__(self, hubspot_call_id: str, company_id: str, recording_url: str, call_date: datetime):
        self.hubspot_call_id = hubspot_call_id
        self.company_id = company_id
        self.recording_url = recording_url
        self.call_date = call_date
        self.call_outcome: Optional[str] = None
        self.assigned_to: Optional[str] = None
        self.is_trigger_call = False
        self.raw_transcript: Optional[str] = None
        self.cleaned_transcript: Optional[str] = None
        self.deepgram_request_id: Optional[str] = None
        self.deepgram_entities: Optional[Dict[str, Any]] = None
        self.deepgram_sentiment: Optional[Dict[str, Any]] = None
        self.deepgram_topics: Optional[Dict[str, Any]] = None
        self.transcription_status = "pending"
        self.analysis_status = "pending"
        self.transcript_judge_verdict: Optional[str] = None
        self.transcript_judge_feedback: Optional[Dict[str, Any]] = None
        self.final_judge_verdict: Optional[str] = None
        self.final_judge_feedback: Optional[Dict[str, Any]] = None

class BANTICScore:
    def __init__(self, 
                 score_budget=0, score_authority=0, score_need=0, score_timeline=0, score_impact=0, score_current_process=0,
                 budget_evidence="", authority_evidence="", need_evidence="", timeline_evidence="", impact_evidence="", current_process_evidence="",
                 budget_info_captured="", authority_info_captured="", need_info_captured="", timeline_info_captured="", impact_info_captured="", current_process_info_captured="",
                 overall_summary="", reasoning="", sdr_coaching_note=""):
        self.score_budget = score_budget
        self.score_authority = score_authority
        self.score_need = score_need
        self.score_timeline = score_timeline
        self.score_impact = score_impact
        self.score_current_process = score_current_process
        
        self.budget_evidence = budget_evidence
        self.authority_evidence = authority_evidence
        self.need_evidence = need_evidence
        self.timeline_evidence = timeline_evidence
        self.impact_evidence = impact_evidence
        self.current_process_evidence = current_process_evidence
        
        self.budget_info_captured = budget_info_captured
        self.authority_info_captured = authority_info_captured
        self.need_info_captured = need_info_captured
        self.timeline_info_captured = timeline_info_captured
        self.impact_info_captured = impact_info_captured
        self.current_process_info_captured = current_process_info_captured
        
        self.overall_summary = overall_summary
        self.reasoning = reasoning
        self.sdr_coaching_note = sdr_coaching_note

class CompanyJourney:
    def __init__(self, company: Company, calls: List[Dict[str, Any]]):
        self.company = company
        self.calls = calls
        self.contacts: List[Contact] = []
        self.dm_contact: Optional[Contact] = None
        self.sdr_name: Optional[str] = None
        self.scheduled_meeting_time: Optional[datetime] = None
        self.bantic_scores: List[BANTICScore] = []
        self.weighted_score: Optional[float] = None
        self.qualification_tier: Optional[str] = None
