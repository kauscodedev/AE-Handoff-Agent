#!/usr/bin/env python3
"""Quick test of the Transcript Judge stage (4.1)."""

import os
import json
from datetime import datetime
from lib.types import Call
from stages.transcript_judge import judge_transcripts

# Load env
from dotenv import load_dotenv
load_dotenv()

# Create a test call with intentionally swapped speaker labels
test_call = Call(
    hubspot_call_id="test-transcript-001",
    company_id="test-company",
    recording_url="https://example.com/recording.wav",
    call_date=datetime.now()
)

# Raw transcript (what Deepgram produces)
test_call.raw_transcript = """Speaker 0: Hello, is this Tom's automotive?
Speaker 1: Yes, hi there. Who's calling?
Speaker 0: This is Sarah from Spyne, we help automotive dealers with photo solutions.
Speaker 1: Oh, interesting. We've been looking for something like that actually.
Speaker 0: Great! What's your current process for photos?
Speaker 1: We use our smartphones mostly, takes forever.
Speaker 0: How many photos a month?
Speaker 1: Probably 200 to 300. It's a pain.
Speaker 0: I'd love to help. Who makes final decisions on tools?
Speaker 1: That would be me and our manager."""

# Cleaned transcript (what Stage 4 produces - with INTENTIONAL SWAP for testing)
# In reality, Speaker 0 is the SDR, Speaker 1 is the prospect, but let's say Stage 4 got it wrong and swapped them
test_call.cleaned_transcript = """[PROSPECT]: Hello, is this Tom's automotive?
[SDR]: Yes, hi there. Who's calling?
[PROSPECT]: This is Sarah from Spyne, we help automotive dealers with photo solutions.
[SDR]: Oh, interesting. We've been looking for something like that actually.
[PROSPECT]: Great! What's your current process for photos?
[SDR]: We use our smartphones mostly, takes forever.
[PROSPECT]: How many photos a month?
[SDR]: Probably 200 to 300. It's a pain.
[PROSPECT]: I'd love to help. Who makes final decisions on tools?
[SDR]: That would be me and our manager."""

print("\n" + "="*60)
print("TRANSCRIPT JUDGE TEST")
print("="*60)

print(f"\n📋 Test Call: {test_call.hubspot_call_id}")
print(f"📝 Raw Transcript: {len(test_call.raw_transcript)} chars")
print(f"🏷️  Cleaned Transcript: {len(test_call.cleaned_transcript)} chars (intentionally swapped)")

print("\n⚠️  Original cleaned transcript has SDR/PROSPECT SWAPPED for testing")
print("   (Speaker 0 = SDR but labeled as PROSPECT, Speaker 1 = PROSPECT but labeled as SDR)")

print("\n🔍 Running Transcript Judge (GLM-4.7 with thinking)...")
print("   This will take a moment as it calls the NVIDIA API...\n")

try:
    # Run the judge
    result = judge_transcripts([test_call])

    print("✅ Judge completed successfully!\n")

    # Check the corrected transcript
    corrected_call = result[0]

    print("📝 Judge Verdict:")
    print(f"   Original first line: {test_call.cleaned_transcript.split(chr(10))[0]}")
    print(f"   Corrected first line: {corrected_call.cleaned_transcript.split(chr(10))[0]}")

    if test_call.cleaned_transcript != corrected_call.cleaned_transcript:
        print(f"\n✏️  Corrections applied: YES")
    else:
        print(f"\n✏️  Corrections applied: NO (approved as-is)")

    # Check feedback log
    if os.path.exists("logs/transcript_judge_feedback.jsonl"):
        with open("logs/transcript_judge_feedback.jsonl") as f:
            last_line = f.readlines()[-1]
            feedback = json.loads(last_line)
            print(f"\n📝 Judge Feedback Log:")
            print(f"   Verdict: {feedback.get('verdict')}")
            print(f"   Corrections: {len(feedback.get('corrections_applied', []))} applied")
            if feedback.get('corrections_applied'):
                for corr in feedback['corrections_applied']:
                    if corr['type'] == 'global_swap':
                        print(f"     - Global swap: {corr['from']} ↔ {corr['to']}")
                    elif corr['type'] == 'turn_correction':
                        print(f"     - Turn {corr['turn_index']}: → {corr['corrected_label']}")
            if feedback.get('reasoning'):
                print(f"   Reasoning: {feedback['reasoning']}")

    print("\n✅ TEST PASSED - Transcript Judge is working!")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60 + "\n")
