"""
Load the showcase plant (Veridian Petrochemicals, two sites, about 160 assets) into the CURRENT stores.

The showcase is what the public demo login works. It lives in the same Supabase, Neo4j, Qdrant and
Elasticsearch as the real data, kept apart by markers (`api/services/tenant.py`), so loading it must
never change anything a real account sees. This script is built around that:

  * DRY RUN BY DEFAULT. With no flag it creates nothing: it reads the dataset files, audits every
    row for a showcase marker, reads the stores to report what is already loaded and whether any id
    would collide with real data, and prints the plan.
  * `--apply` writes. It also needs SHOWCASE_CONFIRM=load-showcase-into-current-stores in the
    environment, so a stray flag cannot start a cloud write. Run it only on the owner's go-ahead.
  * Real-mode counts are taken before and after (assets, documents, conflicts, quarantine, events,
    briefs as seen by a real account) and the run fails loudly if any changed.
  * Idempotent: ids are deterministic, inserts ignore duplicates, a document already in the vault
    (same file name on a showcase site) is not uploaded again.

The data is the `showcase_*` files in `dataset/` (`scripts/showcase/files.py`, written by
`scripts/generate_showcase.py`); nothing is generated here. What goes through the real API, as the demo account (so the same guards a visitor meets apply):
assets, documents (the real OCR, NER, graph and index pipeline) and the nine live events. What is
written directly, with the service role, because no route creates it: aliases (before the documents), the ninety days of
history, conflicts, MoC, quarantine, briefs, knowledge capture and plant states.

    python scripts/load_showcase.py                       # dry run
    SHOWCASE_CONFIRM=load-showcase-into-current-stores python scripts/load_showcase.py --apply
"""

import argparse
import asyncio
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta

sys.path.insert(0, "/app")

import httpx
import structlog
from supabase import create_client

from api.config import Settings
from api.services import tenant
from scripts.showcase import files
from scripts.showcase.files import DocFile
from scripts.showcase.history import unmarked
from scripts.showcase.spec import SITE_A, Asset

log = structlog.get_logger(__name__)

CONFIRM = "load-showcase-into-current-stores"
API_BASE = os.getenv("API_BASE_URL", "http://kairos-backend-api:8000")
DEMO_EMAIL = "demo@kairos.local"
_TERMINAL_STAGES = {"complete", "failed", "review_required", "rejected"}
# Real-mode tables read as a real account sees them, counted before and after.
REAL_COUNTS = (
    ("assets", "asset_id"), ("documents", "document_id"), ("operational_events", "event_id"),
    ("knowledge_conflicts", "asset_id"), ("quarantine_items", "asset_id"), ("moc_items", "asset_id"),
)


# --- pure pieces (tested without any store) ----------------------------------------------------

def depth(asset: Asset, by_id: dict[str, Asset]) -> int:
    d, cur = 0, asset
    while cur.parent:
        d, cur = d + 1, by_id[cur.parent]
    return d


def asset_batches(assets: list[Asset]) -> list[list[Asset]]:
    """Assets grouped by depth, parents first, so every parent exists before its children are posted."""
    by_id = {a.asset_id: a for a in assets}
    levels: dict[int, list[Asset]] = {}
    for a in assets:
        levels.setdefault(depth(a, by_id), []).append(a)
    return [levels[k] for k in sorted(levels)]


def asset_row(a: Asset) -> dict:
    return {"asset_id": a.asset_id, "tag_number": a.tag, "name": a.name, "equipment_class": a.equipment_class,
            "criticality": a.criticality, "site_id": a.site_id, "facility_id": a.facility_id,
            "parent_asset_id": a.parent, "eam_source": "showcase"}


def plan_summary(assets, docs, sc) -> dict:
    return {
        "assets": len(assets), "documents": len(docs),
        **{table: len(rows) for table, rows in sc.tables().items()},
        "live_events": len(sc.live_events),
    }


# --- stores ------------------------------------------------------------------------------------

def real_counts(sb) -> dict[str, int]:
    """Row counts as a real account sees them: showcase rows excluded exactly as `tenant` excludes them."""
    out: dict[str, int] = {}
    for table, col in REAL_COUNTS:
        q = sb.table(table).select(col, count="exact").limit(1)
        if table == "operational_events":
            q = q.not_.in_("site_id", list(tenant.DEMO_SITES))
        elif table == "documents":
            q = q.or_("access_tags->>site_id.is.null,access_tags->>site_id.not.in.(SITE_DEMO,SITE_DEMO_B)")
        elif table == "assets":
            q = q.not_.like("asset_id", f"{tenant.DEMO_PREFIX}*")
        else:
            q = q.or_(f"{col}.is.null,{col}.not.like.{tenant.DEMO_PREFIX}*")
        out[table] = q.execute().count or 0
    return out


def existing_showcase(sb, assets, docs) -> dict:
    """What is already loaded, and any id that would collide with real data."""
    have_assets = {r["asset_id"] for r in (sb.table("assets").select("asset_id").like("asset_id", f"{tenant.DEMO_PREFIX}*").execute().data or [])}
    have_docs = {r["file_name"]: r["document_id"] for r in (
        sb.table("documents").select("document_id, file_name, access_tags")
        .in_("file_name", [d.file_name for d in docs]).execute().data or []
    ) if tenant.is_demo_document(r)}
    aliases = [x.tag for x in assets] + [x.name for x in assets]
    clash = [r["alias"] for r in (sb.table("asset_alias_map").select("alias, canonical_asset_id").in_("alias", aliases).execute().data or [])
             if not tenant.is_demo_id(r["canonical_asset_id"])]
    return {"assets_loaded": len(have_assets), "documents_loaded": have_docs, "alias_clashes_with_real_assets": clash}


def init_demo_stores(settings: Settings) -> None:
    """Create the showcase sibling Qdrant collection (with the payload indexes Qdrant Cloud requires)
    and the Elasticsearch sibling indices. The only place that creates them."""
    from elasticsearch import AsyncElasticsearch
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import Distance, VectorParams

    from api.services.search_engine import SearchEngineService
    from scripts.init_qdrant import PAYLOAD_INDEXES

    async def go() -> None:
        qd = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
        name = tenant.demo_store(settings.QDRANT_COLLECTION_DOCUMENTS)
        try:
            have = {c.name for c in (await qd.get_collections()).collections}
            if name not in have:
                await qd.create_collection(name, vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSION, distance=Distance.COSINE))
                log.info("showcase.qdrant_collection_created", name=name)
            for field, schema in PAYLOAD_INDEXES.items():
                try:
                    await qd.create_payload_index(collection_name=name, field_name=field, field_schema=schema)
                except Exception as exc:  # noqa: BLE001 — already indexed
                    log.info("showcase.qdrant_index_skip", field=field, reason=str(exc)[:60])
        finally:
            await qd.close()
        kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
        if settings.ELASTICSEARCH_USERNAME:
            kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
        es = AsyncElasticsearch(**kwargs)
        try:
            await SearchEngineService(es, settings).ensure_demo_indices()
        finally:
            await es.close()

    asyncio.run(go())


def demo_login(client: httpx.Client, password: str) -> tuple[dict, str]:
    r = client.post("/auth/login", json={"email": DEMO_EMAIL, "password": password})
    r.raise_for_status()
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user_id"]


def set_demo_site(sb, user_id: str) -> bool:
    """Move the demo account to the showcase site, so the UI's site-bound actions (plant state, event
    forms, asset registration, site-wide briefs) default to the showcase plant. Merges into the existing
    `app_metadata` (role and name stay). Returns whether anything changed."""
    user = sb.auth.admin.get_user_by_id(user_id).user
    meta = dict(user.app_metadata or {})
    if meta.get("site_id") == SITE_A:
        return False
    meta["site_id"] = SITE_A
    sb.auth.admin.update_user_by_id(user_id, {"app_metadata": meta})
    return True


def post_assets(client: httpx.Client, headers: dict, assets: list[Asset]) -> None:
    batches = asset_batches(assets)
    for level, batch in enumerate(batches):
        for i in range(0, len(batch), 100):
            chunk = batch[i:i + 100]
            r = client.post("/assets/bulk", json={"assets": [asset_row(a) for a in chunk]}, headers=headers)
            r.raise_for_status()
            log.info("showcase.assets", level=level, sent=len(chunk), response={k: (len(v) if isinstance(v, list) else v) for k, v in r.json().items()})


def ingest_documents(client: httpx.Client, headers: dict, docs: list[DocFile], anchor: datetime, have: dict[str, str]) -> dict[str, str]:
    ids = dict(have)
    for doc in docs:
        if doc.file_name in ids:
            continue
        data = {"document_type": doc.document_type, "authority_level": str(doc.authority), "source_system": "showcase",
                "asset_id": doc.asset_id, "occurred_at": (anchor.replace(microsecond=0) - timedelta(days=doc.age_days)).isoformat()}
        r = client.post("/documents/ingest", data=data, headers=headers, files={"file": (doc.file_name, doc.data(), doc.mime)})
        r.raise_for_status()
        ids[doc.file_name] = r.json()["document_id"]
        log.info("showcase.document", file=doc.file_name, document_id=ids[doc.file_name], status=r.json().get("status"))
    return ids


def wait_for_pipelines(sb, document_ids: list[str], timeout_s: float = 3600.0) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        rows = sb.table("extraction_jobs").select("document_id, pipeline_stage, error").in_("document_id", document_ids).execute().data or []
        pending = [r for r in rows if r.get("pipeline_stage") not in _TERMINAL_STAGES and not r.get("error")]
        if not pending:
            log.info("showcase.pipelines_settled", jobs=len(rows), stages=dict(Counter(r["pipeline_stage"] for r in rows)))
            return
        if time.monotonic() > deadline:
            log.warning("showcase.pipelines_timeout", pending=len(pending))
            return
        time.sleep(10)


def insert_rows(sb, table: str, rows: list[dict], key: str | None) -> None:
    """Insert, ignoring rows that already exist (deterministic ids make a re-run a no-op)."""
    for i in range(0, len(rows), 200):
        chunk = rows[i:i + 200]
        q = sb.table(table).upsert(chunk, on_conflict=key, ignore_duplicates=True) if key else sb.table(table).insert(chunk)
        q.execute()
    log.info("showcase.rows", table=table, rows=len(rows))


def write_aliases(sb, sc) -> None:
    """The alias map, BEFORE any document goes in. The pipeline resolves a tag in a document through the
    confirmed aliases, so with the map missing every tag but the document's own asset is "unresolved": it
    links to nothing and queues a review item. (Loaded after the pipelines, the first load left 77 of those
    and 73 wrong alias guesses behind.)"""
    insert_rows(sb, "asset_alias_map", sc.aliases, "alias")


def write_history(sb, settings: Settings, sc) -> None:
    # Parents before children (foreign keys): events reference assets, which the API created.
    insert_rows(sb, "operational_events", sc.history_events, "event_id")
    insert_rows(sb, "plant_operating_states", sc.plant_states, "id")
    insert_rows(sb, "knowledge_conflicts", sc.conflicts, "conflict_id")
    insert_rows(sb, "moc_items", sc.moc_items, "moc_id")
    insert_rows(sb, "quarantine_items", sc.quarantine, "item_id")
    insert_rows(sb, "elicitation_sessions", sc.elicitation_sessions, "session_id")
    insert_rows(sb, "offboarding_sessions", sc.offboarding_sessions, "id")
    insert_rows(sb, "offboarding_session_items", sc.offboarding_items, "id")
    insert_rows(sb, "briefs", sc.briefs, "brief_id")
    insert_rows(sb, "brief_feedback", sc.brief_feedback, "id")


def materialise_events(settings: Settings, sc) -> None:
    from neo4j import AsyncGraphDatabase

    from api.routers.events import _materialise_event_node

    async def go() -> None:
        driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD))
        try:
            for row in sc.history_events:
                await _materialise_event_node(driver, row["event_id"], row["event_type"], row["occurred_at"], row["asset_id"])
        finally:
            await driver.close()

    asyncio.run(go())
    log.info("showcase.event_nodes", count=len(sc.history_events))


def post_live_events(client: httpx.Client, headers: dict, sc) -> None:
    for route, body in sc.live_events:
        r = client.post(route, json=body, headers=headers)
        log.info("showcase.live_event", route=route, status=r.status_code, body=r.text[:120])


# --- entry point -------------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Load the showcase plant into the current stores.")
    parser.add_argument("--apply", action="store_true", help="write (also needs SHOWCASE_CONFIRM)")
    args = parser.parse_args()

    settings = Settings()
    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    now = datetime.now(UTC)
    ds = files.read(files.showcase_root())
    assets, docs = ds.assets, ds.docs
    sc = files.bind(ds, now=now)
    bad = unmarked(sc)
    if bad:
        raise SystemExit(f"{len(bad)} rows carry no showcase marker, refusing to continue: {bad[:2]}")

    print("Showcase plan:", plan_summary(assets, docs, sc))
    found = existing_showcase(sb, assets, docs)
    print("Already loaded:", {"assets": found["assets_loaded"], "documents": len(found["documents_loaded"])})
    if found["alias_clashes_with_real_assets"]:
        raise SystemExit(f"alias clash with real assets: {found['alias_clashes_with_real_assets']}")
    before = real_counts(sb)
    print("Real-mode counts before:", before)
    if not args.apply:
        print("Dry run: nothing was written. Re-run with --apply and SHOWCASE_CONFIRM to load.")
        return
    if os.getenv("SHOWCASE_CONFIRM") != CONFIRM:
        raise SystemExit(f"--apply needs SHOWCASE_CONFIRM={CONFIRM}")

    password = os.environ["KAIROS_SEED_PASSWORD_DEMO"]
    with httpx.Client(base_url=API_BASE, timeout=300) as client:
        headers, demo_user_id = demo_login(client, password)
        sc = files.bind(ds, now=now, demo_user_id=demo_user_id)  # the demo account's real id, for recipients
        init_demo_stores(settings)
        log.info("showcase.demo_site", changed=set_demo_site(sb, demo_user_id), site=SITE_A)
        post_assets(client, headers, assets)
        write_aliases(sb, sc)  # before the documents: the pipeline resolves their tags through it
        doc_ids = ingest_documents(client, headers, docs, now, found["documents_loaded"])
        wait_for_pipelines(sb, list(doc_ids.values()))
        sc = files.bind(ds, now=now, demo_user_id=demo_user_id, doc_ids=doc_ids)  # sources now name real document ids
        write_history(sb, settings, sc)
        materialise_events(settings, sc)
        post_live_events(client, headers, sc)
    after = real_counts(sb)
    print("Real-mode counts after: ", after)
    if after != before:
        raise SystemExit(f"REAL MODE CHANGED: before {before}, after {after}")
    print("Showcase loaded; real-mode counts unchanged.")


if __name__ == "__main__":
    main()
