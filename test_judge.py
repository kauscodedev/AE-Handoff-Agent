#!/usr/bin/env python3
"""Quick test of the Final Judge stage."""

import os
import json
from datetime import datetime
from lib.types import Call, BANTICScore
from stages.final_judge import judge_bantic_scores

# Load env
from dotenv import load_dotenv
load_dotenv()

# Create a test call with BANTIC score
test_call = Call(
    hubspot_call_id="test-call-001",
    company_id="test-company",
    recording_url="https://example.com/recording.wav",
    call_date=datetime.now()
)
test_call.cleaned_transcript = """
[SDR]: Hi there, good morning. I'm calling about our photo solution.
[PROSPECT]: Yeah, hi. We've been thinking about this. Budget is tight though.
[SDR]: Understood. How many photos a month do you handle?
[PROSPECT]: About 500 to 600. It's been a pain point.
[SDR]: And who would make the final decision on this?
[PROSPECT]: That would be me and the manager.
[SDR]: Great. When could we move forward?
[PROSPECT]: Maybe next quarter if the budget works out.
"""

# Create a test BANTIC score (with some intentionally borderline scores)
test_score = BANTICScore(
    score_budget=1,  # Vague mention of budget
    score_authority=2,  # Prospect + manager involved
    score_need=2,  # Clear mention of pain with photos
    score_timeline=1,  # "Maybe next quarter" is vague
    score_impact=0,  # No impact discussed
    score_current_process=2,  # "Been a pain point" for ~500-600 photos
    budget_evidence="Budget is tight though.",
    authority_evidence="That would be me and the manager.",
    need_evidence="It's been a pain point.",
    timeline_evidence="Maybe next quarter if the budget works out.",
    impact_evidence="",
    current_process_evidence="About 500 to 600. It's been a pain point.",
    overall_summary="Mid-stage deal with qualified prospect and clear need.",
)

print("\n" + "="*60)
print("FINAL JUDGE TEST")
print("="*60)

print(f"\n📋 Test Call: {test_call.hubspot_call_id}")
print(f"📝 Cleaned Transcript: {len(test_call.cleaned_transcript)} chars")

print("\n📊 Original BANTIC Scores:")
print(f"  Budget:        {test_score.score_budget}/3 ('{test_score.budget_evidence[:40]}...')")
print(f"  Authority:     {test_score.score_authority}/3 ('{test_score.authority_evidence[:40]}...')")
print(f"  Need:          {test_score.score_need}/3 ('{test_score.need_evidence[:40]}...')")
print(f"  Timeline:      {test_score.score_timeline}/3 ('{test_score.timeline_evidence[:40]}...')")
print(f"  Impact:        {test_score.score_impact}/3 ('{test_score.impact_evidence[:40]}...')")
print(f"  Current Proc:  {test_score.score_current_process}/3 ('{test_score.current_process_evidence[:40]}...')")

print("\n🔍 Running Final Judge (GLM-4.7 with thinking)...")
print("   This will take a moment as it calls the NVIDIA API...\n")

try:
    # Run the judge
    result = judge_bantic_scores(
        calls_with_scores=[(test_call, test_score)],
        company_name="Test Company"
    )

    print("✅ Judge completed successfully!\n")

    # Check if the score changed
    call_after, score_after = result[0]

    print("📊 Judge Verdict:")
    print(f"  Budget:        {score_after.score_budget}/3 (changed: {test_score.score_budget != score_after.score_budget})")
    print(f"  Authority:     {score_after.score_authority}/3 (changed: {test_score.score_authority != score_after.score_authority})")
    print(f"  Need:          {score_after.score_need}/3 (changed: {test_score.score_need != score_after.score_need})")
    print(f"  Timeline:      {score_after.score_timeline}/3 (changed: {test_score.score_timeline != score_after.score_timeline})")
    print(f"  Impact:        {score_after.score_impact}/3 (changed: {test_score.score_impact != score_after.score_impact})")
    print(f"  Current Proc:  {score_after.score_current_process}/3 (changed: {test_score.score_current_process != score_after.score_current_process})")

    # Check feedback log
    import os
    if os.path.exists("logs/judge_feedback.jsonl"):
        with open("logs/judge_feedback.jsonl") as f:
            last_line = f.readlines()[-1]
            feedback = json.loads(last_line)
            print(f"\n📝 Judge Feedback Log:")
            print(f"  Verdict: {feedback.get('verdict')}")
            print(f"  Changes: {len(feedback.get('changes', []))} field(s) modified")
            if feedback.get('overall_comment'):
                print(f"  Comment: {feedback['overall_comment']}")

    print("\n✅ TEST PASSED - Judge is working!")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60 + "\n")
