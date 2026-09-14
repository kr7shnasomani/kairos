"""
Load the Kairos golden dataset (``dataset/``) into a running stack.

Drives the *real* API endpoints so the true pipeline runs (OCR -> NER -> graph ->
index for documents; brief assembly for events) — the same path a production
ingest would take. Everything is idempotent: assets MERGE, documents dedup by
SHA-256, so re-running is safe.

Run inside the API container (dataset mounted at /app/dataset):
  docker exec kairos-backend-api python scripts/load_demo_dataset.py
  docker exec kairos-backend-api python scripts/load_demo_dataset.py --fast   # skip document pipeline

Canonical ground truth for these facts: dataset/00_Reference/00_KAIROS_CANON.md
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import structlog
from supabase import create_client

from api.config import settings

log = structlog.get_logger(__name__)

API_BASE = os.getenv("API_BASE_URL", "http://kairos-backend-api:8000")
DATASET_DIR = Path(os.getenv("KAIROS_DATASET_DIR", str(Path(__file__).parent.parent / "dataset")))
SITE_ID = "SITE_001"
FACILITY_ID = "RPC"
CONFIRMED_BY = "admin@kairos.local"
AUTH = {"Authorization": f"Bearer {settings.INTERNAL_API_KEY}"}

# filename -> (document_type, authority_level, asset_id). Derived from dataset_manifest.csv + CANON.
DOCS: list[tuple[str, str, int, str | None]] = [
    # 02_Document_Corpus
    ("02_Document_Corpus/oem_manual_eq1xx_seal.pdf", "oem_manual", 3, "EQ-101"),
    ("02_Document_Corpus/oem_bulletin_fp_sb_2025_04.pdf", "oem_manual", 3, "EQ-101"),
    ("02_Document_Corpus/oem_bulletin_mht_pb_2026_11.pdf", "oem_manual", 3, "HE-301"),
    ("02_Document_Corpus/sop_he_301_04.pdf", "procedure", 4, "HE-301"),
    ("02_Document_Corpus/sop_he_302_04.pdf", "procedure", 4, "HE-302"),
    ("02_Document_Corpus/sop_he_303_04.pdf", "procedure", 4, "HE-303"),
    ("02_Document_Corpus/sop_he_gen_11.pdf", "procedure", 4, None),
    ("02_Document_Corpus/mp_he_hydrotest_03.pdf", "procedure", 4, "HE-301"),
    ("02_Document_Corpus/insp_he301_2025_q4.pdf", "inspection_report", 4, "HE-301"),
    ("02_Document_Corpus/insp_he302_2025_q4.pdf", "inspection_report", 4, "HE-302"),
    ("02_Document_Corpus/inspection_checklist.pdf", "inspection_report", 4, "XV-203"),
    ("02_Document_Corpus/work_order_closeout_form.pdf", "inspection_report", 5, "EQ-101"),
    ("02_Document_Corpus/ptw_v247.pdf", "ptw", 4, "V-247"),
    ("02_Document_Corpus/regulatory_clause_excerpts.pdf", "regulation", 1, None),
    ("02_Document_Corpus/pid_line3_isolation_boundary.png", "pid_drawing", 3, "V-247"),
    # EQ-1xx pump-family maintenance history — the EQ-102 electrical-insulation counterfactual
    # narrative lives here; tagged EQ-102 so it is searchable under that asset (EQ-101 history is
    # already covered by other docs). Text/CSV is decoded directly by the OCR service.
    ("01_Structured_Backbone/work_orders_eq101_family.csv", "inspection_report", 5, "EQ-102"),
    # 03_Multiformat_Variants (OCR / multi-script stress)
    ("03_Multiformat_Variants/handwritten_inspection_note.png", "inspection_report", 5, "EQ-101"),
    ("03_Multiformat_Variants/handwritten_shift_log.png", "shift_log", 5, None),
    ("03_Multiformat_Variants/scanned_inspection_degraded.png", "inspection_report", 4, "HE-302"),
    ("03_Multiformat_Variants/scanned_oem_bulletin_degraded.png", "oem_manual", 3, "HE-301"),
    ("03_Multiformat_Variants/shift_log.txt", "shift_log", 5, None),
]


def _criticality(raw: str) -> str:
    """Map the canon's criticality vocabulary onto the API's enum."""
    low = raw.lower()
    if "safety" in low:
        return "safety_critical"
    if low.startswith(("critical", "high")):
        return "critical"
    return "non_critical"


def load_assets(client: httpx.Client) -> None:
    """Register canonical assets from the structured backbone CSV via POST /assets."""
    path = DATASET_DIR / "01_Structured_Backbone" / "asset_registry.csv"
    with path.open() as fh:
        for row in csv.DictReader(fh):
            body = {
                "asset_id": row["asset_tag"],
                "tag_number": row["asset_tag"],
                "name": row["description"],
                "equipment_class": row["equipment_class"].strip().lower().replace(" - ", "_").replace(" ", "_"),
                "criticality": _criticality(row["criticality"]),
                "site_id": SITE_ID,
                "facility_id": FACILITY_ID,
                "eam_source": "manual",
                "confirmed_by_user_id": CONFIRMED_BY,
            }
            r = client.post("/assets/", json=body, headers=AUTH)
            log.info("load.asset", asset=row["asset_tag"], status=r.status_code)


def load_aliases() -> None:
    """Seed canonical tag aliases from the structured backbone CSV into asset_alias_map.

    No POST-alias endpoint exists (only the NER pipeline writes aliases), so insert directly
    via the service client. Idempotent: `alias` is globally UNIQUE, so upsert on conflict.
    """
    path = DATASET_DIR / "01_Structured_Backbone" / "alias_table.csv"
    if not path.exists():
        log.warning("load.aliases.missing", file=str(path))
        return
    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    with path.open() as fh:
        rows = [{
            "canonical_asset_id": r["canonical_asset_id"],
            "alias": r["alias"],
            "alias_source": f"golden_dataset:{r.get('source_context', '')}"[:200],
            "confidence": 1.0,
            "confirmed": True,
            "confirmed_by": CONFIRMED_BY,
        } for r in csv.DictReader(fh)]
    sb.table("asset_alias_map").upsert(rows, on_conflict="alias").execute()
    log.info("load.aliases", count=len(rows))


def ingest_documents(client: httpx.Client) -> None:
    """Push every corpus document through the real POST /documents/ingest pipeline."""
    for rel, doc_type, authority, asset_id in DOCS:
        path = DATASET_DIR / rel
        if not path.exists():
            log.warning("load.doc.missing", file=rel)
            continue
        data = {"document_type": doc_type, "authority_level": str(authority), "source_system": "demo_dataset"}
        if asset_id:
            data["asset_id"] = asset_id
        with path.open("rb") as fh:
            r = client.post("/documents/ingest", data=data, files={"file": (path.name, fh)}, headers=AUTH)
        log.info("load.doc", file=path.name, type=doc_type, status=r.status_code)


# Dataset events name people ("Suresh Yadav"), but a brief is addressed to a user id and only its
# recipient (or the site) can see it — so on the 2026-09-13 reload 3 of 4 briefs reached no inbox,
# including the PTW brief the dual sign-off starts from. Each dataset role is played by the seeded
# persona with that job; the person's name stays in the event payload.
_PERSONA_EMAILS = {
    "technician": "field_worker@kairos.local",
    "engineer": "engineer@kairos.local",
    "shift_lead": "reliability@kairos.local",
}


def _persona_ids() -> dict[str, str]:
    """Seeded user id per dataset role. Missing personas fall back to the site-wide address."""
    try:
        sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        by_email = {u.email: str(u.id) for u in sb.auth.admin.list_users()}
    except Exception as exc:  # noqa: BLE001 — briefs still load, addressed site-wide
        log.warning("load.persona_lookup_failed", error=str(exc))
        by_email = {}
    site_wide = f"site-{SITE_ID}"
    return {role: by_email.get(email, site_wide) for role, email in _PERSONA_EMAILS.items()}


def _event_endpoint_and_body(ev: dict, personas: dict[str, str]) -> tuple[str, dict] | None:
    """Translate a dataset event JSON into (endpoint, request body) for the matching API model."""
    p = ev.get("payload", {})
    common = {"source_system": ev.get("source_system", "demo_dataset"), "site_id": SITE_ID, "occurred_at": ev.get("timestamp")}
    etype = ev.get("event_type")
    asset = ev.get("canonical_asset_id")
    if etype in ("work_order_created", "recurring_failure_detected"):
        return "/events/work-order", {**common,
            "work_order_id": p.get("work_order_id", ev["event_id"]), "asset_id": asset,
            "failure_code": p.get("failure_code", "UNKNOWN"), "description": p.get("failure_description", ""),
            "assigned_technician_id": personas["technician"], "priority": str(p.get("priority", "normal")).lower()}
    if etype == "ptw_generated":
        return "/events/ptw", {**common,
            "ptw_id": p.get("ptw_id", ev["event_id"]), "work_area": p.get("work_location", ""),
            "asset_ids": [a for a in [asset, *p.get("isolation_boundary", [])] if a],
            "ptw_type": "isolation", "issuing_engineer_id": personas["engineer"]}
    if etype == "shift_handover":
        return "/events/shift-handover", {**common,
            "outgoing_shift_lead_id": p.get("outgoing_shift_lead", "unknown"),
            "incoming_shift_lead_id": personas["shift_lead"],
            "handover_time": ev.get("timestamp")}
    return None


def replay_events(client: httpx.Client) -> None:
    """Replay the canonical operational events; deviation flags go through their own endpoint."""
    events_dir = DATASET_DIR / "04_Events_And_Quarantine"
    personas = _persona_ids()
    for path in sorted(events_dir.glob("event_*.json")):
        ev = json.loads(path.read_text())
        mapped = _event_endpoint_and_body(ev, personas)
        if not mapped:
            log.warning("load.event.unmapped", file=path.name, type=ev.get("event_type"))
            continue
        endpoint, body = mapped
        r = client.post(endpoint, json=body, headers=AUTH)
        log.info("load.event", file=path.name, endpoint=endpoint, status=r.status_code)

    # The PG-18 quarantine item is a physical deviation flag (freezes downstream briefs).
    dev = events_dir / "quarantine_pg18_deviation.json"
    if dev.exists():
        d = json.loads(dev.read_text())
        # The reviewer reads this text verbatim in the quarantine queue, so send the observation
        # itself — json.dumps of the whole record rendered a raw JSON blob as the item's content.
        src = d.get("payload", d)
        text = src.get("content_translation_en") or src.get("content_text_original") or json.dumps(src)
        body = {"asset_id": d.get("canonical_asset_id", "PG-18"),
                "description": text[:500],
                "reported_by": "Suresh Yadav", "affected_topology_path": "Line3/Sec2/PG-18"}
        r = client.post("/events/deviation-flag", json=body, headers=AUTH)
        log.info("load.deviation", status=r.status_code)


def submit_voice(client: httpx.Client) -> None:
    """Submit the field voice note for Whisper transcription -> NER -> quarantine."""
    voice = DATASET_DIR / "04_Events_And_Quarantine" / "voice_note_eq101.mp3"
    if not voice.exists():
        return
    with voice.open("rb") as fh:
        r = client.post("/elicitation/WO-2026-0714/voice",
                        data={"submitted_by": "Suresh Yadav"},
                        files={"file": (voice.name, fh, "audio/mpeg")}, headers=AUTH)
    log.info("load.voice", status=r.status_code)


def create_offboarding(client: httpx.Client) -> None:
    """Register a departing expert so the off-boarding knowledge-transfer flow is demoable.

    Idempotent: skips if a programme for this expert already exists. Session questions
    are generated asynchronously by the offboarding Celery worker (NIM), so they appear
    a few seconds after the programme is created.
    """
    email = "ramesh.kumar@kairos.local"
    existing = client.get("/elicitation/offboarding", headers=AUTH)
    if existing.status_code == 200 and any(
        p.get("personnel_email") == email for p in existing.json().get("items", [])
    ):
        log.info("load.offboarding.skip_existing")
        return
    body = {
        "personnel_id": "EXPERT-RKUMAR",
        "personnel_email": email,
        "retirement_date": "2026-09-30",
        "session_interval_days": 7,
    }
    r = client.post("/elicitation/offboarding", json=body, headers=AUTH)
    log.info("load.offboarding", status=r.status_code)


def _seed_validation_corpus() -> None:
    """Seed the Layer-0 NER ground-truth set (idempotent) once documents are indexed."""
    try:
        import asyncio as _aio

        from scripts.seed_validation_corpus import _run as _seed
        _aio.run(_seed())
    except Exception as exc:  # noqa: BLE001 — non-fatal for the demo load
        log.warning("load.valcorpus_failed", error=str(exc))


def _verify_demo_topology() -> None:
    """
    Mark the demo P&ID's extracted elements as engineer-verified.

    Layer 5 instrumentation coverage is derived from **verified** topology only, and Layer 10's
    telemetry check is gated on that coverage. Without this step every asset would correctly but
    unhelpfully report `coverage_type: "none"` on a freshly loaded dataset, because no human has
    reviewed the drawing yet — the demo would show the honest answer to a question nobody had
    asked. This stands in for the engineer walking the review queue.

    Idempotent, and it only ever promotes elements of the demo drawing.
    """
    try:
        import asyncio as _aio

        from neo4j import AsyncGraphDatabase

        from api.services.graph import GraphService
        from api.services.topology import TopologyVerificationService

        async def _run() -> None:
            sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
            # A GraphService is REQUIRED here, not optional. `TopologyVerificationService.graph`
            # defaults to None, and with it None `verify_elements` updates the Supabase review row and
            # silently skips promoting the graph edge — the two stores then disagree about what a
            # human approved. One event loop for the whole step: the async driver binds to the loop
            # that first uses it, so a separate `asyncio.run()` per call closed that loop under it
            # ("Event loop is closed", 2026-09-13).
            driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD))
            try:
                svc = TopologyVerificationService(sb, graph=GraphService(driver, settings.NEO4J_DATABASE))
                manifests = (
                    sb.table("quarantine_items").select("content").like("content", "PID_TOPOLOGY_MANIFEST:%").execute()
                )
                for row in manifests.data or []:
                    document_id = row["content"].split("PID_TOPOLOGY_MANIFEST:", 1)[1]
                    statuses = await svc.element_statuses(document_id)
                    decisions = [{"element_id": eid, "decision": "confirmed"} for eid in statuses]
                    if decisions:
                        await svc.verify_elements(document_id, decisions, reviewer_id="demo-loader")
                        log.info("load.topology_verified", document_id=document_id, elements=len(decisions))
            finally:
                await driver.close()

        _aio.run(_run())
    except Exception as exc:  # noqa: BLE001 — non-fatal for the demo load
        log.warning("load.topology_verify_failed", error=str(exc))


def _seed_canonical_conflicts() -> None:
    """Register the canon's Flow C contradiction: HE-3xx max operating pressure, 18.5 vs 16.2 bar.

    Ingestion cannot detect it. A KNOWLEDGE_EDGE carries no asserted value, so the pipeline only
    writes provenance edges (`DOCUMENTED_BY`), which by design never conflict — comparing values would
    be an edge schema change (see `GraphService.NON_ASSERTING_RELATIONSHIPS`). Without this, a fresh
    load had zero conflicts and the governance → MoC flow had nothing to act on. Every row is marked
    with its origin so it is never mistaken for a detected conflict. Idempotent per asset.
    """
    import uuid
    from datetime import UTC, datetime, timedelta

    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    wanted = [
        "oem_bulletin_mht_pb_2026_11.pdf", "sop_he_301_04.pdf", "sop_he_302_04.pdf", "sop_he_303_04.pdf",
        "insp_he301_2025_q4.pdf", "insp_he302_2025_q4.pdf", "mp_he_hydrotest_03.pdf",
    ]
    rows = sb.table("documents").select("document_id, file_name").in_("file_name", wanted).execute().data or []
    doc = {r["file_name"]: r["document_id"] for r in rows}
    bulletin = doc.get("oem_bulletin_mht_pb_2026_11.pdf")
    if not bulletin:
        log.warning("load.conflicts_skipped", reason="MHT-PB-2026-11 not ingested")
        return
    origin = "golden dataset canon §3 (1-Jun-2026 bulletin) and §4 (Flow C) — registered by loader, not detected"
    blast = [d for d in (doc.get("insp_he301_2025_q4.pdf"), doc.get("insp_he302_2025_q4.pdf"),
                         doc.get("mp_he_hydrotest_03.pdf")) if d]
    now = datetime.now(UTC)
    for asset, sop_file in (("HE-301", "sop_he_301_04.pdf"), ("HE-302", "sop_he_302_04.pdf"), ("HE-303", "sop_he_303_04.pdf")):
        sop = doc.get(sop_file)
        if not sop:
            continue
        existing = (
            sb.table("knowledge_conflicts").select("conflict_id")
            .eq("asset_id", asset).eq("parameter", "max_operating_pressure").limit(1).execute().data
        )
        if existing:
            continue
        conflict = sb.table("knowledge_conflicts").insert({
            "track": "engineering",
            "asset_id": asset,
            "parameter": "max_operating_pressure",
            "source_a": {"document_id": sop, "file_name": sop_file, "authority_level": 4, "value": "18.5 bar", "origin": origin},
            "source_b": {"document_id": bulletin, "file_name": "oem_bulletin_mht_pb_2026_11.pdf", "authority_level": 3,
                         "value": "16.2 bar", "origin": origin},
            "authority_a": 4,
            "authority_b": 3,
            "severity": "major",
            "status": "pending_moc",
            "sla_deadline": (now + timedelta(hours=24)).isoformat(),
        }).execute().data[0]
        sb.table("moc_items").insert({
            "moc_id": f"MOC-{uuid.uuid4().hex[:8].upper()}",
            "conflict_id": conflict["conflict_id"],
            "asset_id": asset,
            "description": (
                f"{asset} maximum operating pressure: Meridian bulletin MHT-PB-2026-11 (L3) revises the limit to "
                f"16.2 bar; {sop_file} (L4) still states 18.5 bar. Update the SOP and re-check dependent records."
            ),
            "conflicting_sources": [{"document_id": sop, "value": "18.5 bar"}, {"document_id": bulletin, "value": "16.2 bar"}],
            "blast_radius": blast,
            "status": "draft",
        }).execute()
        log.info("load.conflict_registered", asset=asset, conflict_id=conflict["conflict_id"])


# Stages a job never leaves on its own. Anything else is still running in Temporal.
_TERMINAL_STAGES = {"complete", "review_required"}


def _wait_for_pipelines(timeout_s: float = 900.0) -> None:
    """Block until every extraction job has settled.

    Ingest answers 202 and the Temporal pipeline runs afterwards, so the steps after it raced the
    pipeline: on the 2026-09-13 reload the validation corpus seeded 0 labels because no document
    text was indexed yet. A job that recorded an error is settled too — waiting on it would hang.
    """
    import time

    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    deadline = time.monotonic() + timeout_s
    while True:
        rows = sb.table("extraction_jobs").select("pipeline_stage, error").execute().data or []
        pending = [r for r in rows if r.get("pipeline_stage") not in _TERMINAL_STAGES and not r.get("error")]
        if not pending:
            log.info("load.pipelines_settled", jobs=len(rows))
            return
        if time.monotonic() > deadline:
            log.warning("load.pipelines_timeout", pending=len(pending), jobs=len(rows))
            return
        time.sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the Kairos golden demo dataset into a running stack.")
    parser.add_argument("--fast", action="store_true", help="Skip the document pipeline + voice (structured backbone + events only).")
    args = parser.parse_args()

    if not DATASET_DIR.exists():
        raise SystemExit(f"Dataset not found at {DATASET_DIR}. Mount ./dataset into the container or set KAIROS_DATASET_DIR.")

    with httpx.Client(base_url=API_BASE, timeout=120) as client:
        load_assets(client)
        load_aliases()
        if not args.fast:
            ingest_documents(client)
            create_offboarding(client)
            _wait_for_pipelines()
            _seed_validation_corpus()
            _verify_demo_topology()
            _seed_canonical_conflicts()
        # Events last: a brief is assembled from what the graph holds when its event arrives. Replayed
        # first, every brief was built on an empty graph — the PTW brief listed no evidence and no
        # isolation topology, because the drawing had not been ingested or verified yet.
        replay_events(client)
        # After the events: transcription links the note to its asset through the WO-2026-0714
        # work-order event, so submitted before it the note landed in quarantine with no asset.
        if not args.fast:
            submit_voice(client)
    log.info("load.done", fast=args.fast)


if __name__ == "__main__":
    main()
