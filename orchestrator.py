#!/usr/bin/env python3
"""
AE Handoff Brief Agent — Orchestrator
10-Stage Pipeline (with Stage 4.1, 4.5, and 5.5):
1. HubSpot Watcher — polls for "C - Meeting Scheduled" calls
2. Fetch Agent — gets company + contacts + call data
3. Transcription — submits to Deepgram Nova-3
4. Clean Transcript — labels speakers with OpenAI
4.1. Transcript Judge — GLM-4.7 verifies speaker labels, corrects if wrong
4.5. DM Discovery — identifies decision maker from transcripts
5. BANTIC Analysis — scores on 6 dimensions with OpenAI
5.5. Final Judge — GLM-4.7 reviews BANTIC scores, revises if clearly wrong
6. Score Module — calculates weighted score (Python, no LLM)
7. AE Brief Agent — generates handoff brief with OpenAI

All data persists to Supabase at each stage.
PID lockfile prevents duplicate instances.
"""

import os
import sys
import time
import atexit
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Stages
from stages.watcher import watch_for_meeting_scheduled
from stages.fetch_agent import fetch_company_journey
from stages.transcription import transcribe_calls
from stages.clean_transcript import clean_calls
from stages.transcript_judge import judge_transcripts
from stages.dm_discovery import discover_dm
from stages.bantic_analysis import analyze_calls
from stages.final_judge import judge_bantic_scores
from stages.score_module import score_company_journey
from stages.ae_brief_agent import generate_ae_brief, save_brief

# Configure Logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/orchestrator.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load Environment Variables
load_dotenv()

# PID Lockfile to prevent duplicate instances
LOCK_FILE = "/tmp/ae_handoff_orchestrator.lock"

# Operating Hours (IST: Indian Standard Time)
IST = timezone(timedelta(hours=5, minutes=30))
OPERATING_START_HOUR = 17   # 5pm IST
OPERATING_END_HOUR = 4      # 4am IST (next calendar day)

def is_within_operating_hours() -> bool:
    """Check if current time is within operating hours (17:00–04:00 IST)."""
    h = datetime.now(IST).hour
    return h >= OPERATING_START_HOUR or h < OPERATING_END_HOUR

def seconds_until_window_opens() -> int:
    """Calculate seconds until next operating window opens (17:00 IST)."""
    now = datetime.now(IST)
    next_open = now.replace(hour=OPERATING_START_HOUR, minute=0, second=0, microsecond=0)
    if now >= next_open:  # already past 5pm today, next open is tomorrow
        next_open += timedelta(days=1)
    return max(0, int((next_open - now).total_seconds()))

def acquire_lock():
    """Prevent duplicate orchestrator instances using a PID lockfile."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                pid = int(f.read().strip())
            # Check if process with that PID is running
            import subprocess
            result = subprocess.run(["ps", "-p", str(pid)], capture_output=True)
            if result.returncode == 0:
                logger.error(f"Orchestrator already running as PID {pid}. Exiting.")
                sys.exit(1)
        except (ValueError, FileNotFoundError):
            pass

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.remove(LOCK_FILE) if os.path.exists(LOCK_FILE) else None)
    logger.info(f"Acquired lock as PID {os.getpid()}")

def process_company(company_id: str, hubspot_call_id: str):
    """Executes the full pipeline for a single company."""
    logger.info(f"\n================================================================================")
    logger.info(f"Processing company: {company_id} (trigger call: {hubspot_call_id})")
    logger.info(f"================================================================================\n")

    try:
        # Stage 2: Fetch Agent
        journey = fetch_company_journey(company_id, hubspot_call_id)
        if not journey:
            logger.error(f"✗ Fetch failed for {company_id}")
            return False

        if not journey.calls:
            logger.info(f"  No calls found for {company_id}")
            return False

        # Prepare calls for processing
        calls_to_process = []
        for call_data in journey.calls:
            # Create Call object
            from lib.types import Call
            call = Call(
                hubspot_call_id=call_data["hubspot_call_id"],
                company_id=company_id,
                recording_url=call_data.get("recording_url", ""),
                call_date=datetime.fromisoformat(call_data["call_date"]) if call_data.get("call_date") else None
            )
            calls_to_process.append((call, call_data))

        if not calls_to_process:
            logger.info(f"  All calls already analyzed for {company_id}")
            return False

        logger.info(f"  Processing {len(calls_to_process)} connected calls")

        # Stage 3: Transcription
        logger.info("\n→ Processing transcriptions...")
        transcribed_calls = []
        for call, call_data in calls_to_process:
            if call_data.get("raw_transcript"):
                logger.info(f"  Using existing transcript for {call.hubspot_call_id[:12]}")
                call.raw_transcript = call_data["raw_transcript"]
                call.deepgram_entities = call_data.get("deepgram_entities")
                call.deepgram_sentiment = call_data.get("deepgram_sentiment")
                call.deepgram_topics = call_data.get("deepgram_topics")
                call.transcription_status = "completed"
                transcribed_calls.append(call)
            elif call.recording_url:
                # Submit to Deepgram
                transcribe_calls([call])
                if call.raw_transcript:
                    transcribed_calls.append(call)
            else:
                logger.warning(f"  ⚠️ Call {call.hubspot_call_id} is missing a recording URL!")

        if not transcribed_calls:
            logger.warning("  No transcripts available")
            return False

        # Stage 4: Clean Transcripts
        logger.info("\n→ Cleaning transcripts...")
        prospect_name = journey.dm_contact.name if journey.dm_contact else "Prospect"
        cleaned_calls_list = clean_calls(
            transcribed_calls, 
            company_name=journey.company.name,
            sdr_name=journey.sdr_name or "SDR",
            prospect_name=prospect_name
        )

        if not cleaned_calls_list:
            logger.warning("  No transcripts cleaned")
            return False

        # Stage 4.1: Transcript Judge
        logger.info("\n→ Reviewing speaker labels...")
        cleaned_calls_list = judge_transcripts(cleaned_calls_list)

        # Stage 4.5: DM Discovery from transcripts
        logger.info("\n→ Discovering decision maker...")
        discover_dm(journey, cleaned_calls_list)

        # Stage 5: BANTIC Analysis
        logger.info("\n→ Running BANTIC analysis...")
        calls_with_scores = analyze_calls(cleaned_calls_list)
        if calls_with_scores:
            # Stage 5.5: Final Judge
            calls_with_scores = judge_bantic_scores(calls_with_scores, company_name=journey.company.name)

            # Stage 6: Score Module
            score_result = score_company_journey(calls_with_scores, trigger_call_id=hubspot_call_id)
            
            # Stage 7: AE Brief
            brief = generate_ae_brief(journey, score_result)
            if brief:
                logger.info("\n→ Saving brief...")
                save_brief(journey.company.name, brief, hubspot_call_id, journey.company.hubspot_id)
                logger.info(f"✓ Complete: {journey.company.name}")
                return True
        
        return False

    except Exception as e:
        logger.error(f"✗ Pipeline error: {e}", exc_info=True)
        return False


def run_orchestrator(interval: int = 60):
    """
    Main orchestrator loop.
    Polls HubSpot every `interval` seconds for new Meeting Scheduled calls.
    Only runs during operating hours (17:00–04:00 IST).
    """
    logger.info(f"Starting orchestrator loop (interval: {interval}s)")
    logger.info("Operating hours: 17:00–04:00 IST daily")

    while True:
        try:
            # Check if within operating hours
            if not is_within_operating_hours():
                wait = seconds_until_window_opens()
                h, m = divmod(wait // 60, 60)
                logger.info(f"Outside operating hours. Sleeping {h}h {m}m until 17:00 IST...")
                time.sleep(wait)
                continue

            # Stage 1: HubSpot Watcher
            logger.info(f"\n[{datetime.now(timezone.utc).isoformat()}] Checking for pending calls...")
            pending_calls = watch_for_meeting_scheduled(limit=10)

            if pending_calls:
                logger.info(f"✓ Found {len(pending_calls)} pending calls")
                for call_data in pending_calls:
                    hubspot_call_id = call_data["hubspot_call_id"]
                    company_id = call_data["hubspot_company_id"]
                    process_company(company_id, hubspot_call_id)
                    time.sleep(2)  # Brief pause between companies
            else:
                logger.info("No pending calls found")

            logger.info(f"Next check in {interval}s...\n")
            time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Orchestrator stopped by user")
            break
        except Exception as e:
            logger.error(f"Orchestrator error: {e}", exc_info=True)
            logger.info(f"Recovering in {interval}s...")
            time.sleep(interval)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AE Handoff Brief Agent Orchestrator")
    parser.add_argument("--once", action="store_true", help="Run one iteration only")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default: 60)")

    args = parser.parse_args()

    # Acquire lock to prevent duplicate instances
    acquire_lock()

    if args.once:
        logger.info("Running orchestrator once...")
        try:
            pending_calls = watch_for_meeting_scheduled(limit=10)
            if pending_calls:
                logger.info(f"Found {len(pending_calls)} pending calls")
                for call_data in pending_calls:
                    hubspot_call_id = call_data["hubspot_call_id"]
                    company_id = call_data["hubspot_company_id"]
                    process_company(company_id, hubspot_call_id)
                    time.sleep(1)
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
    else:
        run_orchestrator(interval=args.interval)
