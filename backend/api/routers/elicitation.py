"""
Elicitation Engine router — Layer 6: Tacit Knowledge Elicitation.
Triggers graph-derived micro-interviews at work order closeout and routes
operator responses into quarantine for human review and graph promotion.
"""

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any

import shortuuid
import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from api.config import get_settings
from api.dependencies import (
    CurrentUserDep,
    OffboardingSessionIdDep,
    SupabaseDep,
    TemporalDep,
    demo_llm_budget,
)
from api.services import tenant

log = structlog.get_logger(__name__)
router = APIRouter()

_ELICITATION_QUEUE = "kairos-elicitation"

# Staff who administer off-boarding programmes. Anyone else may see a programme only if they are
# the person being offboarded (see `_require_staff_or_subject`).
_STAFF_ROLES = frozenset({"engineer", "reliability", "admin"})

_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _safe_segment(value: str | None, default: str) -> str:
    """One storage-path segment from a client-supplied name: base name only, `[A-Za-z0-9._-]`.

    The upload goes through the service-role client, which bypasses storage policies, so a name like
    `../../x` must never reach the object path. Leading dots are stripped so `..` and hidden names
    collapse to the default.
    """
    base = PurePosixPath((value or "").replace("\\", "/")).name
    return _UNSAFE_PATH_CHARS.sub("_", base).lstrip(".")[:100] or default


def _is_subject(session: dict, user: dict) -> bool:
    """Is `user` the person this programme is about? Matched on id, or on e-mail as a fallback."""
    uid = user.get("user_id")
    email = (user.get("email") or "").lower()
    return bool(uid and session.get("personnel_id") == uid) or bool(
        email and (session.get("personnel_email") or "").lower() == email
    )


def _is_staff_or_subject(session: dict, user: dict) -> bool:
    return tenant.has_role(user, *_STAFF_ROLES) or _is_subject(session, user)


def _require_staff_or_subject(session: dict, user: dict) -> None:
    """403 unless the caller is staff or the person being offboarded. Programme rows carry the
    person's e-mail and retirement date, and completing an item ends the knowledge-capture interview."""
    if not _is_staff_or_subject(session, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Off-boarding programmes are restricted to staff and the person concerned.",
        )


class ElicitationTriggerRequest(BaseModel):
    work_order_id: str
    asset_id: str
    failure_code: str
    equipment_class: str
    resolution_time_hours: float = 0.0
    novel_troubleshooting: bool = False
    triggered_by: str = "system"


class ElicitationAnswer(BaseModel):
    """
    One answer in a micro-interview.

    Typed explicitly because the previous `list[dict[str, str]]` gave callers no contract: an
    integer index produced `"Input should be a valid string"` pointing at a key the caller had
    invented, with nothing to say what the real key was. `question` carries the question *text*
    (the questions are a `string[]`, so the text is the identifier); `question_index` is accepted
    as an alternative for callers that held the position instead.
    """

    answer: str
    question: str | None = None
    question_index: int | None = None


class ElicitationResponseRequest(BaseModel):
    responses: list[ElicitationAnswer]
    # Accepted for older clients and ignored: the submitter is always the authenticated user.
    submitted_by: str | None = None


@router.post("/trigger", dependencies=[Depends(demo_llm_budget)], summary="Trigger micro-interview if elicitation conditions are met")
async def trigger_elicitation(
    payload: ElicitationTriggerRequest,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    temporal: TemporalDep,
) -> dict:
    reasons: list[str] = []
    tenant.guard_asset(current_user, payload.asset_id)

    # (a) Rare failure code — count occurrences in operational_events for this equipment class
    events_result = await asyncio.to_thread(
        lambda: tenant.scope_site(
            supabase.table("operational_events")
            .select("event_id", count="exact")
            .filter("payload->>failure_code", "eq", payload.failure_code),
            current_user,
        ).execute()
    )
    failure_count = events_result.count or 0
    if failure_count < 3:
        reasons.append(f"rare_failure_code (count={failure_count})")

    # (b) Resolution time above 90th percentile for this failure type
    times_result = await asyncio.to_thread(
        lambda: tenant.scope_site(
            supabase.table("operational_events")
            .select("payload")
            .filter("payload->>failure_code", "eq", payload.failure_code),
            current_user,
        ).execute()
    )
    times = [
        float(r["payload"]["resolution_time_hours"])
        for r in (times_result.data or [])
        if r.get("payload", {}).get("resolution_time_hours") is not None
    ]
    if times and payload.resolution_time_hours > 0:
        times_sorted = sorted(times)
        p90_idx = max(0, int(0.9 * len(times_sorted)) - 1)
        p90 = times_sorted[p90_idx]
        if payload.resolution_time_hours > p90:
            reasons.append(f"slow_resolution (hours={payload.resolution_time_hours:.1f}, p90={p90:.1f})")

    # (c) Novel troubleshooting flagged by the engineer
    if payload.novel_troubleshooting:
        reasons.append("novel_troubleshooting")

    if not reasons:
        return {"triggered": False, "reasons": [], "message": "No elicitation conditions met"}

    workflow_id = f"elicitation-{payload.work_order_id}-{shortuuid.uuid()[:6]}"
    await temporal.start_workflow(
        "MicroInterviewWorkflow",
        {
            "work_order_id": payload.work_order_id,
            "asset_id": payload.asset_id,
            "failure_code": payload.failure_code,
            "triggered_by": payload.triggered_by,
        },
        id=workflow_id,
        task_queue=_ELICITATION_QUEUE,
    )

    log.info("elicitation.triggered",
             work_order_id=payload.work_order_id,
             workflow_id=workflow_id,
             reasons=reasons)
    return {"triggered": True, "workflow_id": workflow_id, "reasons": reasons}


@router.get("/{work_order_id}/questions", summary="Return generated questions for mobile delivery")
async def get_questions(
    work_order_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    result = await asyncio.to_thread(
        lambda: supabase.table("elicitation_sessions")
        .select("session_id, work_order_id, asset_id, questions, status, created_at")
        .eq("work_order_id", work_order_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No elicitation session found for work order '{work_order_id}'",
        )
    session = result.data[0]
    return {
        "session_id": session["session_id"],
        "work_order_id": session["work_order_id"],
        "asset_id": session["asset_id"],
        "status": session["status"],
        "questions": session["questions"],
        "created_at": session["created_at"],
    }


@router.post("/{work_order_id}/responses", summary="Submit Q&A responses into quarantine")
async def submit_responses(
    work_order_id: str,
    payload: ElicitationResponseRequest,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    temporal: TemporalDep,
) -> dict:
    # Fetch session to get asset_id and questions for session_context
    session_result = await asyncio.to_thread(
        lambda: supabase.table("elicitation_sessions")
        .select("session_id, asset_id, questions")
        .eq("work_order_id", work_order_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    session = session_result.data[0] if session_result.data else {}
    asset_id = session.get("asset_id") or ""
    tenant.guard_asset(current_user, asset_id)
    questions = session.get("questions") or []

    workflow_id = f"elicitation-store-{work_order_id}-{shortuuid.uuid()[:6]}"
    result: dict[str, Any] = await temporal.execute_workflow(
        "StoreElicitationResponseWorkflow",
        {
            "work_order_id": work_order_id,
            "asset_id": asset_id,
            # Workflow input must be plain JSON, not Pydantic models.
            "responses": [r.model_dump(exclude_none=True) for r in payload.responses],
            "submitted_by": current_user.get("user_id", "unknown"),
            "questions": questions,
        },
        id=workflow_id,
        task_queue=_ELICITATION_QUEUE,
    )

    log.info("elicitation.responses_submitted",
             work_order_id=work_order_id,
             item_id=result.get("item_id"))
    return result


@router.post(
    "/{work_order_id}/voice", dependencies=[Depends(demo_llm_budget)],
    summary="Ingest voice note — transcribe via Whisper, route to quarantine",
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_voice_note(
    work_order_id: str,
    file: UploadFile,
    submitted_by: str | None = Form(None),  # ignored: the submitter is the authenticated user
    current_user: CurrentUserDep = None,
    supabase: SupabaseDep = None,
) -> dict:
    settings = get_settings()
    submitted_by = current_user.get("user_id", "unknown")
    await tenant.guard_work_order(supabase, current_user, work_order_id)

    # Reject oversized audio as early as the body allows: the declared size first, then a running
    # total over 1 MB chunks, so an oversized or unsized upload is never held in memory whole.
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    too_big = HTTPException(
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit."
    )
    if file.size is not None and file.size > max_bytes:
        raise too_big
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise too_big
        chunks.append(chunk)
    audio_bytes = b"".join(chunks)
    sha256 = hashlib.sha256(audio_bytes).hexdigest()

    # SHA-256 dedup: skip re-upload if identical file already stored
    existing = await asyncio.to_thread(
        lambda: supabase.table("quarantine_items")
        .select("item_id")
        .eq("session_context->>sha256", sha256)
        .limit(1)
        .execute()
    )
    if existing.data:
        return {
            "status": "duplicate",
            "item_id": existing.data[0]["item_id"],
            "message": "Identical audio already in quarantine",
        }

    safe_name = _safe_segment(file.filename, "audio.wav")
    storage_path = f"voice_notes/{_safe_segment(work_order_id, 'unknown')}/{sha256[:8]}_{safe_name}"
    try:
        await asyncio.to_thread(
            lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
                storage_path,
                audio_bytes,
                {"content-type": file.content_type or "audio/wav"},
            )
        )
    except Exception as exc:
        if "Duplicate" not in str(exc) and "already exists" not in str(exc):
            raise
        log.info("elicitation.voice_note_already_in_storage", storage_path=storage_path)

    from workers.voice_transcription import transcribe_voice_note
    task = transcribe_voice_note.delay(
        work_order_id=work_order_id,
        storage_path=storage_path,
        sha256=sha256,
        submitted_by=submitted_by,
        filename=safe_name,
    )

    log.info("elicitation.voice_note_queued",
             work_order_id=work_order_id,
             storage_path=storage_path,
             task_id=task.id)

    return {
        "status": "accepted",
        "work_order_id": work_order_id,
        "task_id": task.id,
        "storage_path": storage_path,
        "sha256": sha256,
        "message": "Voice note stored. Transcription and NER running asynchronously.",
    }


# =============================================================================
# Off-Boarding Interview Series (Task 31)
# =============================================================================

class OffboardingCreateRequest(BaseModel):
    personnel_id: str
    personnel_email: str
    retirement_date: str  # ISO date YYYY-MM-DD
    session_interval_days: int = 12


class OffboardingResponseRequest(BaseModel):
    item_id: str  # UUID of offboarding_session_items row
    responses: list[dict[str, Any]]  # [{question_index, answer}, ...]
    submitted_by: str | None = None  # accepted and ignored: the submitter is the authenticated user


async def _guard_session(supabase, session_id: str, user: dict) -> None:
    """404 for an unknown programme, 403 unless `user` is staff or the person it is about."""
    result = await asyncio.to_thread(
        lambda: supabase.table("offboarding_sessions")
        .select("personnel_id, personnel_email")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not (result and result.data):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found")
    _require_staff_or_subject(result.data, user)


@router.post("/offboarding", summary="Start off-boarding interview programme", status_code=status.HTTP_201_CREATED)
async def create_offboarding_programme(
    payload: OffboardingCreateRequest,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    # Role gate
    if not tenant.has_role(current_user, "engineer", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="engineer or admin role required")
    tenant.guard_person(current_user, payload.personnel_id)

    # Identify top equipment classes from this person's WO history
    wo_result = await asyncio.to_thread(
        lambda: tenant.scope_site(
            supabase.table("operational_events")
            .select("asset_id")
            .eq("event_type", "work_order_created")
            .filter("payload->>assigned_technician_id", "eq", payload.personnel_id),
            current_user,
        ).execute()
    )
    asset_ids = list({row["asset_id"] for row in (wo_result.data or []) if row.get("asset_id")})

    equipment_families: list[str] = []
    if asset_ids:
        assets_result = await asyncio.to_thread(
            lambda: supabase.table("assets")
            .select("asset_id, equipment_class")
            .in_("asset_id", asset_ids)
            .execute()
        )
        # Count by equipment_class, take top 6
        class_counts: dict[str, int] = {}
        for row in (assets_result.data or []):
            ec = (row.get("equipment_class") or "GENERAL").strip().upper()
            class_counts[ec] = class_counts.get(ec, 0) + 1
        equipment_families = [k for k, _ in sorted(class_counts.items(), key=lambda x: -x[1])][:6]

    # Pad to 6 with site-wide common classes if needed
    if len(equipment_families) < 6:
        all_assets = await asyncio.to_thread(
            lambda: tenant.scope(supabase.table("assets").select("equipment_class"), current_user, "asset_id").execute()
        )
        site_classes = [(r["equipment_class"] or "").strip().upper() for r in (all_assets.data or []) if r.get("equipment_class")]
        for cls in site_classes:
            if cls not in equipment_families:
                equipment_families.append(cls)
            if len(equipment_families) >= 6:
                break

    # Always have at least one family
    if not equipment_families:
        equipment_families = ["GENERAL"]

    # Create offboarding_sessions row
    session_row = await asyncio.to_thread(
        lambda: supabase.table("offboarding_sessions").insert({
            "personnel_id": payload.personnel_id,
            "personnel_email": payload.personnel_email,
            "retirement_date": payload.retirement_date,
            "total_sessions": len(equipment_families),
            "session_interval_days": payload.session_interval_days,
            "status": "scheduled",
            "created_by": current_user.get("user_id", "unknown"),
        }).execute()
    )
    session_id = session_row.data[0]["id"]

    # Create session items and schedule Celery tasks
    now_utc = datetime.now(UTC)
    items_created = []
    for i, family in enumerate(equipment_families):
        scheduled_for = now_utc + timedelta(days=i * payload.session_interval_days)
        # Session 1 fires in 10s for demo/test; rest use proper eta
        if i == 0:
            scheduled_for = now_utc + timedelta(seconds=10)

        item_row = await asyncio.to_thread(
            lambda sf=scheduled_for, fam=family, idx=i: supabase.table("offboarding_session_items").insert({
                "session_id": session_id,
                "session_number": idx + 1,
                "equipment_family": fam,
                "scheduled_for": sf.isoformat(),
                "status": "pending",
                "questions": [],
            }).execute()
        )
        item_id = item_row.data[0]["id"]

        from workers.offboarding import generate_offboarding_questions
        generate_offboarding_questions.apply_async(args=[item_id], eta=scheduled_for)

        items_created.append({"item_id": item_id, "session_number": i + 1, "equipment_family": family, "scheduled_for": scheduled_for.isoformat()})

    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "offboarding_programme_created",
            "entity_type": "offboarding_session",
            "entity_id": session_id,
            "performed_by": current_user.get("user_id", "unknown"),
            "details": {"personnel_id": payload.personnel_id, "personnel_email": payload.personnel_email, "total_sessions": len(equipment_families)},
        }).execute()
    )

    log.info("offboarding.programme_created", session_id=session_id, personnel_id=payload.personnel_id, sessions=len(equipment_families))
    return {"session_id": session_id, "personnel_id": payload.personnel_id, "total_sessions": len(equipment_families), "items": items_created}


@router.get("/offboarding", summary="List all active off-boarding programmes")
async def list_offboarding_programmes(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    result = await asyncio.to_thread(
        lambda: tenant.scope(
            supabase.table("offboarding_sessions")
            .select("id, personnel_id, personnel_email, retirement_date, total_sessions, status, created_at")
            .neq("status", "cancelled"),
            current_user, "personnel_id", nullable=True,
        ).order("created_at", desc=True).execute()
    )
    # Staff see every programme; anyone else sees only the one about them.
    sessions = [s for s in (result.data or []) if _is_staff_or_subject(s, current_user)]

    # Compute completion percentage for each
    items: list[dict[str, Any]] = []
    for s in sessions:
        completed = await asyncio.to_thread(
            lambda sid=s["id"]: supabase.table("offboarding_session_items")
            .select("id", count="exact")
            .eq("session_id", sid)
            .eq("status", "completed")
            .execute()
        )
        items.append({
            **s,
            "sessions_completed": completed.count or 0,
            "completion_pct": round(100 * (completed.count or 0) / max(s["total_sessions"], 1)),
        })

    return {"items": items, "total": len(items)}


@router.get("/offboarding/{session_id}", summary="Get off-boarding programme detail with all session items")
async def get_offboarding_programme(
    session_id: OffboardingSessionIdDep,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    # maybe_single(), not single(): single() raises PGRST116 on zero rows, which made the
    # 404 below unreachable and turned every unknown session into a 500.
    session_result = await asyncio.to_thread(
        lambda: supabase.table("offboarding_sessions").select("*").eq("id", session_id).maybe_single().execute()
    )
    if not (session_result and session_result.data):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found")
    _require_staff_or_subject(session_result.data, current_user)

    items_result = await asyncio.to_thread(
        lambda: supabase.table("offboarding_session_items")
        .select("id, session_number, equipment_family, status, scheduled_for, completed_at")
        .eq("session_id", session_id)
        .order("session_number")
        .execute()
    )
    return {**session_result.data, "session_items": items_result.data or []}


@router.get("/offboarding/{session_id}/questions", summary="Return questions for all items in this off-boarding session")
async def get_offboarding_questions(
    session_id: OffboardingSessionIdDep,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    await _guard_session(supabase, session_id, current_user)
    items_result = await asyncio.to_thread(
        lambda: supabase.table("offboarding_session_items")
        .select("id, session_number, equipment_family, status, questions, scheduled_for")
        .eq("session_id", session_id)
        .order("session_number")
        .execute()
    )
    if not items_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No items found for session '{session_id}'")

    ready = [i for i in items_result.data if i["status"] == "questions_ready"]
    return {
        "session_id": session_id,
        "total_items": len(items_result.data),
        "items_ready": len(ready),
        "items": items_result.data,
    }


@router.post("/offboarding/{session_id}/responses", summary="Submit responses for an off-boarding session item")
async def submit_offboarding_responses(
    session_id: OffboardingSessionIdDep,
    payload: OffboardingResponseRequest,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    # The submitter is the authenticated user; `payload.submitted_by` is accepted and ignored.
    submitter = current_user.get("user_id", "unknown")
    # Only staff or the person being offboarded may answer or complete a programme item.
    await _guard_session(supabase, session_id, current_user)
    await tenant.guard_row(supabase, current_user, "offboarding_sessions", session_id)
    # Fetch the specific session item
    item_result = await asyncio.to_thread(
        lambda: supabase.table("offboarding_session_items")
        .select("id, session_number, equipment_family, questions")
        .eq("id", payload.item_id)
        .eq("session_id", session_id)
        .maybe_single()
        .execute()
    )
    if not (item_result and item_result.data):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item '{payload.item_id}' not found in session '{session_id}'")

    item = item_result.data

    # Fetch session for personnel_id
    session_result = await asyncio.to_thread(
        lambda: supabase.table("offboarding_sessions")
        .select("personnel_id, total_sessions")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    session = (session_result.data if session_result else None) or {}

    # Insert into quarantine_items with offboarding_response input_type
    quarantine_row = await asyncio.to_thread(
        lambda: supabase.table("quarantine_items").insert({
            # A showcase programme's answers hang off the showcase placeholder asset, so they are
            # recognised as showcase and never reach a real reviewer's queue.
            "asset_id": tenant.DEMO_GENERAL_ASSET if tenant.is_demo_id(session.get("personnel_id")) else None,
            "content": json.dumps(payload.responses),
            "input_type": "offboarding_response",
            "submitted_by": submitter,
            "session_context": {
                "session_id": session_id,
                "session_number": item["session_number"],
                "equipment_family": item["equipment_family"],
                "questions": item["questions"],
                "personnel_id": session.get("personnel_id", ""),
            },
        }).execute()
    )
    item_id_q = quarantine_row.data[0]["item_id"]

    # Mark item completed
    now_iso = datetime.now(UTC).isoformat()
    await asyncio.to_thread(
        lambda: supabase.table("offboarding_session_items").update({
            "status": "completed",
            "completed_at": now_iso,
        }).eq("id", payload.item_id).execute()
    )

    # Check if all items complete → mark programme completed
    remaining = await asyncio.to_thread(
        lambda: supabase.table("offboarding_session_items")
        .select("id", count="exact")
        .eq("session_id", session_id)
        .neq("status", "completed")
        .execute()
    )
    if (remaining.count or 0) == 0:
        await asyncio.to_thread(
            lambda: supabase.table("offboarding_sessions").update({"status": "completed"}).eq("id", session_id).execute()
        )

    log.info("offboarding.response_submitted", session_id=session_id, item_id=payload.item_id, quarantine_item_id=item_id_q)
    return {
        "quarantine_item_id": item_id_q,
        "session_id": session_id,
        "item_id": payload.item_id,
        "programme_completed": (remaining.count or 0) == 0,
    }
