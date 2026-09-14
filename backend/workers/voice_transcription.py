"""
Voice transcription worker — Layer 3 / Layer 6.
Celery task: download audio from vault, transcribe via Groq Whisper API,
run NER on transcript, route result to quarantine_items.
"""

import asyncio
import hashlib
import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from supabase import create_client

from workers.celery_app import celery_app

# Workers run outside the FastAPI process — add /app to path for service imports
sys.path.insert(0, "/app")

log = structlog.get_logger(__name__)


def _supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def _run_ner(text: str) -> list:
    try:
        from api.services.ner import NERService
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(NERService().extract_entities(text))
            return result.get("entities", [])
        finally:
            loop.close()
    except Exception as exc:
        log.warning("voice_transcription.ner_failed", error=str(exc))
        return []


@celery_app.task(queue="transcription", name="workers.voice_transcription.transcribe_voice_note")
def transcribe_voice_note(
    work_order_id: str,
    storage_path: str,
    sha256: str,
    submitted_by: str,
    filename: str,
) -> dict[str, Any]:
    log.info("voice_transcription.started",
             work_order_id=work_order_id, storage_path=storage_path)

    sb = _supabase()
    bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "kairos-vault")

    # Download audio bytes from immutable vault
    try:
        audio_bytes = sb.storage.from_(bucket).download(storage_path)
    except Exception as exc:
        log.error("voice_transcription.download_failed", error=str(exc))
        return {"status": "failed", "error": f"download_failed: {exc}"}

    # Integrity check
    actual_hash = hashlib.sha256(audio_bytes).hexdigest()
    if actual_hash != sha256:
        log.error("voice_transcription.hash_mismatch", expected=sha256, actual=actual_hash)
        return {"status": "failed", "error": "hash_mismatch"}

    # Transcribe via Groq Whisper API
    from api.services.whisper import WhisperService
    transcript = WhisperService().transcribe(audio_bytes, filename)
    if not transcript.get("text"):
        log.warning("voice_transcription.empty_transcript",
                    work_order_id=work_order_id, error=transcript.get("error"))
        return {"status": "failed", "error": "empty_transcript", "detail": transcript.get("error")}

    # NER on transcript
    entities = _run_ner(transcript["text"])

    # Resolve asset_id from work order event if available
    asset_id = None
    try:
        wo = sb.table("operational_events") \
            .select("payload") \
            .filter("payload->>work_order_id", "eq", work_order_id) \
            .limit(1).execute()
        if wo.data:
            val = wo.data[0].get("payload", {}).get("asset_id", "")
            asset_id = val if val else None
    except Exception:
        pass

    # The field capture page asks for an "asset / work-order tag", so the tag is often an asset
    # ("EQ-103") rather than a work order. Resolved only via work orders, such a note was quarantined
    # with no asset and never surfaced in that asset's context. Canonical id first, then a confirmed alias.
    if asset_id is None and work_order_id:
        try:
            tag = work_order_id.strip()
            direct = sb.table("assets").select("asset_id").eq("asset_id", tag).limit(1).execute()
            if direct.data:
                asset_id = direct.data[0]["asset_id"]
            else:
                alias = (
                    sb.table("asset_alias_map").select("canonical_asset_id")
                    .eq("alias", tag).eq("confirmed", True).limit(1).execute()
                )
                if alias.data:
                    asset_id = alias.data[0]["canonical_asset_id"]
        except Exception as exc:  # noqa: BLE001 — the note still lands in quarantine, just unlinked
            log.warning("voice_transcription.asset_lookup_failed", tag=work_order_id, error=str(exc))

    # Insert into quarantine_items
    item_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    sb.table("quarantine_items").insert({
        "item_id": item_id,
        "asset_id": asset_id,
        "work_order_id": work_order_id,
        "input_type": "voice_note",
        "content": transcript["text"],
        "submitted_by": submitted_by,
        "submitted_at": now,
        "review_status": "pending",
        "session_context": {
            "language": transcript["language"],
            "confidence": transcript["confidence"],
            "storage_path": storage_path,
            "sha256": sha256,
            "filename": filename,
            "entities": entities,
            "segments": transcript.get("segments", []),
        },
    }).execute()

    log.info("voice_transcription.complete",
             work_order_id=work_order_id,
             item_id=item_id,
             text_length=len(transcript["text"]),
             confidence=transcript["confidence"],
             language=transcript["language"],
             entity_count=len(entities))

    return {
        "status": "complete",
        "item_id": item_id,
        "work_order_id": work_order_id,
        "transcript_length": len(transcript["text"]),
        "confidence": transcript["confidence"],
        "language": transcript["language"],
        "entity_count": len(entities),
    }
