"""
Wipe ALL data from the local datastores (Neo4j, Elasticsearch, Qdrant).

Unlike `purge_test_data.py` (which removes only test-prefixed rows), this empties
every node/document/point — used to return the local stores to a pristine state
before reloading the golden dataset. Schema, indices, and collection configs are kept.
Supabase (cloud) is reset separately via db/maintenance/reset_all_data.sql.

Run inside the API container:
  docker exec kairos-backend-api python scripts/wipe_local_stores.py

Reload afterwards: make seed && make load-dataset
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import structlog
from neo4j import AsyncGraphDatabase

from api.config import settings

log = structlog.get_logger(__name__)


async def wipe() -> None:
    # Neo4j — delete every node + relationship (constraints/indexes survive).
    driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD))
    try:
        summary = (await driver.execute_query("MATCH (n) DETACH DELETE n", database_=settings.NEO4J_DATABASE)).summary
        log.info("wipe.neo4j", nodes_deleted=summary.counters.nodes_deleted)
    finally:
        await driver.close()

    # Elasticsearch — empty each index (mappings kept).
    auth = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD) if settings.ELASTICSEARCH_USERNAME else None
    with httpx.Client(base_url=settings.ELASTICSEARCH_URL, auth=auth, timeout=30) as es:
        for idx in (settings.ELASTICSEARCH_INDEX_ASSETS, settings.ELASTICSEARCH_INDEX_DOCUMENTS, settings.ELASTICSEARCH_INDEX_EVENTS):
            r = es.post(f"/{idx}/_delete_by_query", params={"conflicts": "proceed", "ignore_unavailable": "true"},
                        json={"query": {"match_all": {}}})
            log.info("wipe.es", index=idx, deleted=r.json().get("deleted") if r.status_code < 300 else r.status_code)

    # Qdrant — delete all points in each collection (config kept). Empty filter matches all.
    # Qdrant Cloud rejects unauthenticated calls with 403 — without the key this wiped nothing and still
    # printed `wipe.done`, leaving stale vectors for documents that no longer exist anywhere else.
    qd_headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
    with httpx.Client(base_url=settings.QDRANT_URL, headers=qd_headers, timeout=30) as qd:
        for col in (settings.QDRANT_COLLECTION_KNOWLEDGE, settings.QDRANT_COLLECTION_DOCUMENTS):
            r = qd.post(
                f"/collections/{col}/points/delete", params={"wait": "true"}, json={"filter": {"must": []}}
            )
            if r.status_code >= 300:
                log.error("wipe.qdrant_failed", collection=col, status=r.status_code, body=r.text[:200])
                sys.exit(1)
            log.info("wipe.qdrant", collection=col, status=r.status_code)

    log.info("wipe.done")


if __name__ == "__main__":
    asyncio.run(wipe())
