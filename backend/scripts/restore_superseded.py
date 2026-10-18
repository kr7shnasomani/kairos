"""
Undo a supersede that should never have happened, using the record the supersede itself wrote.

`POST /documents/{id}/supersede` marks the old document superseded in Supabase, closes its graph
edges (`valid_to` set to the moment of supersession, `verification_status` 'superseded'), flags its
Elasticsearch document and Qdrant chunks `superseded`, points the replacement's `version_chain` at
it, and writes a `document_superseded` audit row. This reverses exactly those writes and nothing
else: only edges closed at that row's timestamp reopen, and they reopen as `unverified` (the status
every edge starts with; an earlier verification is not recorded, so none is claimed).

Written for 2026-09-14, when the QA sweep's `tools/e2e_flows.sh --mutate` superseded the golden
`sop_he_gen_11.pdf` with its own test upload (`implementation/status.md` P34). A legitimate
supersede is undone by a newer document, never by this.

Elasticsearch is per host: run it once locally and once on the server. Supabase, Neo4j and Qdrant
are shared, so the second run finds nothing left to change there and only flags its own index.

    python scripts/restore_superseded.py DOC-AMJ6I6W8ZTCJ                 # dry run: prints the plan
    RESTORE_CONFIRM=DOC-AMJ6I6W8ZTCJ python scripts/restore_superseded.py DOC-AMJ6I6W8ZTCJ --apply
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, "/app")

from elasticsearch import Elasticsearch
from neo4j import AsyncGraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from supabase import create_client

from api.config import Settings

OPEN = "9999-12-31T23:59:59+00:00"


def supersede_record(audit_rows: list[dict]) -> dict | None:
    """The newest `document_superseded` row: its timestamp is when the edges were closed."""
    rows = [r for r in audit_rows if r.get("action") == "document_superseded"]
    return max(rows, key=lambda r: r["timestamp"]) if rows else None


async def closed_edges(settings: Settings, document_id: str, closed_at: str, *, reopen: bool) -> int:
    cypher = (
        "MATCH ()-[r:KNOWLEDGE_EDGE {document_id: $doc}]->() "
        "WHERE r.verification_status = 'superseded' AND r.valid_to = $closed "
        + ("SET r.valid_to = $open, r.verification_status = 'unverified' " if reopen else "")
        + "RETURN count(r) AS n"
    )
    driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD))
    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(cypher, doc=document_id, closed=closed_at, open=OPEN)
            return (await result.single())["n"]
    finally:
        await driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Undo a wrongful supersede.")
    parser.add_argument("document_id")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    doc = args.document_id

    s = Settings()
    sb = create_client(s.SUPABASE_URL, s.SUPABASE_SERVICE_ROLE_KEY)
    rows = sb.table("documents").select("document_id, file_name, status").eq("document_id", doc).execute().data
    if not rows:
        raise SystemExit(f"{doc}: no such document")
    audit = sb.table("audit_log").select("action, details, timestamp").eq("entity_id", doc).execute().data or []
    record = supersede_record(audit)
    if record is None:
        raise SystemExit(f"{doc}: no document_superseded audit row, so there is no supersede to undo")
    replacement = (record.get("details") or {}).get("new_document_id")
    closed_at = record["timestamp"]
    # The edges carry the route's own clock, a moment before the audit row; match on the stored value.
    edge_closed_at = asyncio.run(_edge_close_time(s, doc))

    es = Elasticsearch(hosts=[s.ELASTICSEARCH_URL])
    es_status = es.get(index=s.ELASTICSEARCH_INDEX_DOCUMENTS, id=doc, _source=["status"])["_source"].get("status")
    q = QdrantClient(url=s.QDRANT_URL, api_key=s.QDRANT_API_KEY, timeout=30)
    chunk_filter = Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=doc))])
    chunks, _ = q.scroll(s.QDRANT_COLLECTION_DOCUMENTS, scroll_filter=chunk_filter, limit=500, with_payload=["status"])
    edges = asyncio.run(closed_edges(s, doc, edge_closed_at, reopen=False)) if edge_closed_at else 0

    print(f"Document {doc} ({rows[0]['file_name']}): Supabase {rows[0]['status']}, this host's ES {es_status}, "
          f"Qdrant {sorted({c.payload.get('status') for c in chunks})} over {len(chunks)} chunk(s)")
    print(f"Superseded at {closed_at} by {replacement}; {edges} edge(s) closed at {edge_closed_at} would reopen as unverified")
    if not args.apply:
        print("Dry run: nothing changed. Re-run with --apply and RESTORE_CONFIRM set to the document id.")
        return
    if os.getenv("RESTORE_CONFIRM") != doc:
        raise SystemExit(f"--apply needs RESTORE_CONFIRM={doc}")

    already = rows[0]["status"] == "active"
    sb.table("documents").update({"status": "active"}).eq("document_id", doc).execute()
    if replacement:
        sb.table("documents").update({"version_chain": None}).eq("document_id", replacement).eq("version_chain", doc).execute()
    reopened = asyncio.run(closed_edges(s, doc, edge_closed_at, reopen=True)) if edge_closed_at else 0
    q.set_payload(s.QDRANT_COLLECTION_DOCUMENTS, payload={"status": "active"}, points=chunk_filter)
    es.update(index=s.ELASTICSEARCH_INDEX_DOCUMENTS, id=doc, body={"doc": {"status": "active"}})
    if not already:  # the shared stores change once; a second host's run only flags its own index
        sb.table("audit_log").insert({
            "action": "document_restored", "entity_type": "document", "entity_id": doc,
            "performed_by": "scripts/restore_superseded.py",
            "details": {"undid_supersede_at": closed_at, "replacement": replacement, "edges_reopened": reopened},
        }).execute()
    print(f"Restored: Supabase active, {reopened} edge(s) reopened, Qdrant and this host's ES flagged active.")


async def _edge_close_time(settings: Settings, document_id: str) -> str | None:
    """The `valid_to` the supersede stamped on this document's edges (one value, from one call)."""
    driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD))
    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                "MATCH ()-[r:KNOWLEDGE_EDGE {document_id: $doc}]->() WHERE r.verification_status = 'superseded' "
                "RETURN collect(DISTINCT r.valid_to) AS stamps", doc=document_id,
            )
            stamps = (await result.single())["stamps"]
            if len(stamps) > 1:
                raise SystemExit(f"{document_id}: edges closed at {len(stamps)} different times; refusing to guess")
            return stamps[0] if stamps else None
    finally:
        await driver.close()


if __name__ == "__main__":
    main()
