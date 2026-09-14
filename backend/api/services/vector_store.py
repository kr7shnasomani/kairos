"""
Vector store service — Qdrant client wrapper (Layer 11: Semantic Retrieval).
"""

from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from api.config import Settings

log = structlog.get_logger(__name__)


class VectorStoreService:
    """
    Qdrant vector store — semantic search over extracted knowledge fragments.
    Two collections:
    - kairos_knowledge: extracted facts and graph-linked knowledge fragments
    - kairos_documents: full document chunks for RAG-style retrieval
    """

    def __init__(self, client: AsyncQdrantClient, settings: Settings):
        self.client = client
        self.settings = settings

    async def ensure_collections(self) -> None:
        """Creates Qdrant collections if they don't exist. Called at startup."""
        existing = await self.client.get_collections()
        collection_names = {c.name for c in existing.collections}
        for collection_name in [
            self.settings.QDRANT_COLLECTION_KNOWLEDGE,
            self.settings.QDRANT_COLLECTION_DOCUMENTS,
        ]:
            if collection_name not in collection_names:
                await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.settings.EMBEDDING_DIMENSION,
                        distance=Distance.COSINE,
                    ),
                )
                log.info("qdrant.collection_created", name=collection_name)

    async def upsert(
        self,
        collection: str,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Upserts a vector point with payload metadata."""
        await self.client.upsert(
            collection_name=collection,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )

    async def mark_superseded(self, collection: str, document_id: str) -> None:
        """
        Flags every chunk of a document as superseded so it drops out of default retrieval.

        Payload update, never a delete: the vault is immutable and a time-travel query still
        has to be able to reach these chunks.
        """
        await self.client.set_payload(
            collection_name=collection,
            payload={"status": "superseded"},
            points=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]),
        )

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        asset_id: str | None = None,
        authority_min: int = 5,
        include_quarantine: bool = False,
        quarantine_only: bool = False,
        include_superseded: bool = False,
        document_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search with optional payload filtering.
        Filters: asset_id (or one of `document_ids`, the documents the graph links to that asset),
        authority_level <= authority_min, quarantine status, document status.
        quarantine_only=True: return only quarantine items (for explicit quarantine retrieval pass).

        `include_superseded=False` (the default) drops chunks whose document has been superseded —
        ARCHITECTURE.md §8: superseded documents "never appear in default query results as if they
        were current". Callers doing a time-travel query pass True, because a document that was
        active at the as-of date is a correct hit for that date.
        """
        must_conditions = []

        if asset_id:
            asset_scope = FieldCondition(key="asset_id", match=MatchValue(value=asset_id))
            if document_ids:
                # Both keys carry a KEYWORD payload index (scripts/init_qdrant.py) — required on Cloud.
                linked = FieldCondition(key="document_id", match=MatchAny(any=document_ids))
                must_conditions.append(Filter(should=[asset_scope, linked]))
            else:
                must_conditions.append(asset_scope)
        if quarantine_only:
            must_conditions.append(FieldCondition(key="is_quarantine", match=MatchValue(value=True)))
        elif not include_quarantine:
            must_conditions.append(FieldCondition(key="is_quarantine", match=MatchValue(value=False)))

        # must_not, not must status="active": points indexed before `status` was added to the
        # payload have no such key, and Qdrant treats a missing key as non-matching. Requiring
        # "active" would silently drop every pre-existing chunk; excluding "superseded" keeps
        # them visible and still removes the ones that were explicitly closed.
        must_not_conditions = (
            [] if include_superseded
            else [FieldCondition(key="status", match=MatchValue(value="superseded"))]
        )

        query_filter = (
            Filter(must=must_conditions, must_not=must_not_conditions)
            if (must_conditions or must_not_conditions)
            else None
        )

        results = await self.client.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

        return [
            {
                "point_id": str(r.id),
                "score": r.score,
                "payload": r.payload,
            }
            for r in results
            if r.payload.get("authority_level", 5) <= authority_min
        ]
