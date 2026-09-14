"""
Search engine service — Elasticsearch exact search (Layer 11).
Handles tag number, part number, document ID, and regulatory clause lookup.
"""

from typing import Any

import structlog
from elasticsearch import AsyncElasticsearch

from api.config import Settings

log = structlog.get_logger(__name__)


class SearchEngineService:
    """
    Elasticsearch-backed exact and keyword search.
    Handles structured queries where precision matters over recall:
    - Equipment tag numbers (P-101, EQ-247)
    - Part numbers and material codes
    - Document IDs and revision references
    - Regulatory clause references (OISD-117 Clause 4.2.1)
    """

    def __init__(self, client: AsyncElasticsearch, settings: Settings):
        self.client = client
        self.settings = settings

    async def ensure_indices(self) -> None:
        """Creates ES indices with mappings if they don't exist."""
        indices = {
            self.settings.ELASTICSEARCH_INDEX_ASSETS: self._asset_mapping(),
            self.settings.ELASTICSEARCH_INDEX_DOCUMENTS: self._document_mapping(),
            self.settings.ELASTICSEARCH_INDEX_EVENTS: self._event_mapping(),
        }
        for index_name, mapping in indices.items():
            exists = await self.client.indices.exists(index=index_name)
            if not exists:
                await self.client.indices.create(index=index_name, body=mapping)
                log.info("elasticsearch.index_created", index=index_name)

    async def search(
        self,
        query: str,
        index: str | None = None,
        asset_id: str | None = None,
        limit: int = 10,
        include_superseded: bool = False,
        document_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Exact and full-text search. Prioritizes exact tag number matches.

        With `asset_id`, a hit must be filed under that asset **or** be one of `document_ids` — the
        documents the graph links to it (see `SearchService.hybrid_search`).

        `include_superseded=False` (the default) drops superseded documents — ARCHITECTURE.md §8:
        they "never appear in default query results as if they were current". Time-travel callers
        pass True, because a document active at the as-of date is a correct hit for that date.
        """
        indices = index or f"{self.settings.ELASTICSEARCH_INDEX_DOCUMENTS},{self.settings.ELASTICSEARCH_INDEX_ASSETS}"

        must_clauses: list[Any] = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["tag_number^3", "document_id^3", "clause_ref^3", "title^2", "content"],
                    "type": "best_fields",
                }
            }
        ]
        if asset_id:
            scope: list[Any] = [{"term": {"asset_id": asset_id}}]
            if document_ids:
                scope.append({"terms": {"document_id": document_ids}})
            must_clauses.append({"bool": {"should": scope, "minimum_should_match": 1}})

        bool_query: dict[str, Any] = {"must": must_clauses}
        if not include_superseded:
            # must_not, not must status=active: this query also spans kairos_assets, whose
            # documents carry no `status` field at all. Requiring "active" would exclude every
            # asset hit; excluding "superseded" leaves them untouched.
            bool_query["must_not"] = [{"term": {"status": "superseded"}}]

        body = {
            "query": {"bool": bool_query},
            "size": limit,
            # Many fragments spanning the whole doc so the snippet captures facts far from the
            # query terms (e.g. an OISD/PESO list under a "regulatory standards" header the query
            # matched), not just the top-scoring header cluster. Feeds richer context to synthesis.
            "highlight": {
                "fields": {
                    "content": {"fragment_size": 240, "number_of_fragments": 8},
                    "title": {},
                }
            },
        }

        try:
            response = await self.client.search(index=indices, body=body)
            hits = response["hits"]["hits"]
            return [
                {
                    "document_id": h["_source"].get("document_id"),
                    "asset_id": h["_source"].get("asset_id"),
                    "title": h["_source"].get("title"),
                    "document_type": h["_source"].get("document_type", "unknown"),
                    "snippet": " … ".join(h.get("highlight", {}).get("content", [])) or (h["_source"].get("content", "")[:220]),
                    "score": h["_score"],
                    "authority_level": h["_source"].get("authority_level", 5),
                    "status": h["_source"].get("status", "active"),
                }
                for h in hits
            ]
        except Exception as e:
            log.error("elasticsearch.search_failed", error=str(e))
            return []

    def _asset_mapping(self) -> dict:
        return {
            "mappings": {
                "properties": {
                    "asset_id": {"type": "keyword"},
                    "tag_number": {"type": "keyword"},
                    "name": {"type": "text"},
                    "equipment_class": {"type": "keyword"},
                    "site_id": {"type": "keyword"},
                }
            }
        }

    def _document_mapping(self) -> dict:
        return {
            "mappings": {
                "properties": {
                    "document_id": {"type": "keyword"},
                    "asset_id": {"type": "keyword"},
                    "title": {"type": "text"},
                    "content": {"type": "text", "analyzer": "standard"},
                    "document_type": {"type": "keyword"},
                    "authority_level": {"type": "integer"},
                    "status": {"type": "keyword"},
                    "ingested_at": {"type": "date"},
                }
            }
        }

    def _event_mapping(self) -> dict:
        return {
            "mappings": {
                "properties": {
                    "event_id": {"type": "keyword"},
                    "asset_id": {"type": "keyword"},
                    "event_type": {"type": "keyword"},
                    "occurred_at": {"type": "date"},
                }
            }
        }
