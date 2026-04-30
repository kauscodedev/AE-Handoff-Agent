import logging
import os
import requests
import json
from typing import Optional, Dict, Any
from lib.types import Call
from lib.supabase_client import update_call_fields

logger = logging.getLogger(__name__)

DEEPGRAM_API_URL = "https://api.deepgram.com/v1/listen"

def get_deepgram_headers():
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY not set")
    return {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json"
    }

def submit_to_deepgram(call: Call) -> Optional[str]:
    """
    Stage 3: Transcription Agent - Submit to Deepgram Nova-3
    Submits recording URL and returns request_id.
    Deepgram Nova-3 is synchronous - result returned immediately.
    """
    if not call.recording_url or call.recording_url.strip() == "":
        logger.warning(f"Empty recording URL for {call.hubspot_call_id}")
        return None

    payload = {"url": call.recording_url}
    params = {
        "model": "nova-3",
        "language": "en",
        "diarize": "true",
        "smart_format": "true",
        "punctuate": "true",
        "detect_entities": "true",
        "sentiment": "true",
        "topics": "true",
        "intents": "true",
        "numerals": "true",
        "filler_words": "true",
        "utterances": "true",
    }

    try:
        response = requests.post(
            DEEPGRAM_API_URL,
            headers=get_deepgram_headers(),
            json=payload,
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            logger.error(f"Deepgram API error {response.status_code}: {response.text[:200]}")
            return None

        result = response.json()
        request_id = result.get("request_id") or result.get("metadata", {}).get("request_id")

        if not request_id:
            logger.error(f"No request_id in Deepgram response for {call.hubspot_call_id}")
            logger.debug(f"Deepgram response keys: {list(result.keys())}")
            return None

        # Process and store result immediately (Deepgram is synchronous)
        deepgram_data = process_deepgram_response(result)
        if deepgram_data:
            call.raw_transcript = deepgram_data["transcript"]
            call.deepgram_request_id = request_id
            call.deepgram_entities = deepgram_data["entities"]
            call.deepgram_sentiment = deepgram_data["sentiment"]
            call.deepgram_topics = deepgram_data["topics"]
            call.transcription_status = "completed"
            logger.info(f"✓ Transcribed {call.hubspot_call_id[:12]}")
            return request_id

        return None

    except Exception as e:
        logger.error(f"Exception submitting to Deepgram: {e}")
        return None

def process_deepgram_response(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract transcript and intelligence from Deepgram response."""
    try:
        if "results" not in result or "channels" not in result["results"]:
            logger.error("Invalid Deepgram response structure")
            return None

        channel = result["results"]["channels"][0]
        alternative = channel["alternatives"][0]

        transcript = alternative.get("transcript", "")
        confidence = alternative.get("confidence", 0.0)
        entities = alternative.get("entities", [])
        sentiment = alternative.get("sentiment")
        topics = alternative.get("topics", [])
        intents = alternative.get("intents", [])

        return {
            "transcript": transcript,
            "confidence": confidence,
            "entities": entities,
            "sentiment": sentiment,
            "topics": topics,
            "intents": intents
        }

    except Exception as e:
        logger.error(f"Error processing Deepgram response: {e}")
        return None

def transcribe_calls(calls: list) -> list:
    """Submit a batch of calls to Deepgram for transcription."""
    logger.info(f"→ Stage 3: Transcription Agent for {len(calls)} calls")
    transcribed = []
    for call in calls:
        if submit_to_deepgram(call):
            # Persist transcription data to Supabase
            update_call_fields(call.hubspot_call_id, {
                "raw_transcript": call.raw_transcript,
                "transcription_status": "completed",
                "deepgram_request_id": call.deepgram_request_id,
                "deepgram_entities": call.deepgram_entities,
                "deepgram_sentiment": call.deepgram_sentiment,
                "deepgram_topics": call.deepgram_topics
            })
            transcribed.append(call)
    logger.info(f"✓ Stage 3 complete: {len(transcribed)}/{len(calls)} transcribed")
    return transcribed
