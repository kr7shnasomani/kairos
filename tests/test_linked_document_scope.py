"""Service-free: an asset-scoped search also reaches documents the graph links to that asset."""

from qdrant_client.models import FieldCondition, Filter

from api.services.search_engine import SearchEngineService
from api.services.search_service import SearchService
from api.services.vector_store import VectorStoreService


class _Settings:
    ELASTICSEARCH_INDEX_DOCUMENTS = "docs"
    ELASTICSEARCH_INDEX_ASSETS = "assets"


async def test_es_scope_is_primary_asset_or_linked_document():
    captured = {}

    class FakeES:
        async def search(self, index, body, **kwargs):
            captured["body"] = body
            return {"hits": {"hits": []}}

    await SearchEngineService(FakeES(), _Settings()).search("seal failures", asset_id="EQ-101", document_ids=["DOC-CSV"])

    scope = captured["body"]["query"]["bool"]["must"][1]["bool"]
    assert scope["minimum_should_match"] == 1
    assert scope["should"] == [{"term": {"asset_id": "EQ-101"}}, {"terms": {"document_id": ["DOC-CSV"]}}]


class _FakeQdrant:
    def __init__(self):
        self.kwargs = {}

    async def search(self, **kwargs):
        self.kwargs = kwargs
        return []


async def test_qdrant_scope_is_primary_asset_or_linked_document():
    client = _FakeQdrant()
    await VectorStoreService(client, None).search("c", [0.1], asset_id="EQ-101", document_ids=["DOC-CSV"])

    scope = client.kwargs["query_filter"].must[0]
    assert isinstance(scope, Filter)
    assert [c.key for c in scope.should] == ["asset_id", "document_id"]


async def test_qdrant_without_links_keeps_the_plain_asset_filter():
    client = _FakeQdrant()
    await VectorStoreService(client, None).search("c", [0.1], asset_id="EQ-101")

    scope = client.kwargs["query_filter"].must[0]
    assert isinstance(scope, FieldCondition) and scope.key == "asset_id"


def _service(graph):
    calls = {}

    class Engine:
        async def search(self, query, **kw):
            calls["es"] = kw
            return []

    class Vector:
        async def search(self, collection, vector, **kw):
            calls.setdefault("qdrant", kw)
            return []

    class LLM:
        async def embed(self, text, task=None):
            return [0.1]

    svc = SearchService.__new__(SearchService)
    svc.engine, svc.vector, svc.graph, svc.llm, svc.supabase = Engine(), Vector(), graph, LLM(), None
    return svc, calls


async def test_hybrid_search_hands_graph_linked_documents_to_both_text_searches():
    class Graph:
        async def get_asset_knowledge_at(self, asset_id, **kw):
            return [
                {"edge": {"document_id": "DOC-SOP"}, "target": {}},
                {"edge": {"document_id": "DOC-CSV"}, "target": {}},
                {"edge": {"document_id": "DOC-CSV"}, "target": {}},
            ]

    svc, calls = _service(Graph())
    await svc.hybrid_search("seal failures", "docs", "EQ-101", 5, False, None, 5)

    assert calls["es"]["document_ids"] == ["DOC-CSV", "DOC-SOP"]
    assert calls["qdrant"]["document_ids"] == ["DOC-CSV", "DOC-SOP"]


def test_own_documents_rank_ahead_of_linked_ones_within_an_authority_level():
    from api.models.document import SearchResult

    def r(doc_id, asset, authority=5):
        return SearchResult(
            document_id=doc_id, asset_id=asset, document_type="shift_log", title="", snippet="",
            authority_level=authority, status="active", relevance_score=0.0, retrieval_method="exact",
        )

    svc = SearchService.__new__(SearchService)
    # The linked shift log ranks first in its source; the asset's own closeout form ranks second.
    out = svc._fuse([[r("DOC-SHIFT-LOG", None), r("DOC-CLOSEOUT", "EQ-101"), r("DOC-SOP", None, authority=4)]], 2, asset_id="EQ-101")

    # Relevance keeps the two best; within level 5 the asset's own document is listed ahead of the linked one.
    assert [x.document_id for x in out] == ["DOC-CLOSEOUT", "DOC-SHIFT-LOG"]


def test_a_relevant_low_authority_record_is_not_cut_by_better_ranked_but_less_relevant_ones():
    from api.models.document import SearchResult

    def r(doc_id, authority):
        return SearchResult(
            document_id=doc_id, asset_id="P-1", document_type="manual", title="", snippet="",
            authority_level=authority, status="active", relevance_score=0.0, retrieval_method="exact",
        )

    svc = SearchService.__new__(SearchService)
    # The failure-history card (L5) is the second most relevant of five; the limit is three.
    ranked_by_relevance = [r("DOC-MANUAL", 3), r("DOC-FAILURES", 5), r("DOC-SOP-A", 4), r("DOC-SOP-B", 4), r("DOC-SOP-C", 4)]
    out = svc._fuse([ranked_by_relevance], 3, asset_id="P-1")

    assert [x.document_id for x in out] == ["DOC-MANUAL", "DOC-SOP-A", "DOC-FAILURES"]  # kept, listed after the higher levels


def test_a_provenance_stub_never_takes_a_slot_on_its_own():
    graph = [
        {"edge": {"document_id": "DOC-REGULATION", "relationship_type": "DOCUMENTED_BY"}},   # no text hit
        {"edge": {"document_id": "DOC-CLOSEOUT", "relationship_type": "DOCUMENTED_BY"}},     # text also found it
        {"edge": {"document_id": "DOC-BULLETIN", "relationship_type": "SUPERSEDES"}},        # asserts a fact
    ]
    es = [{"document_id": "DOC-CLOSEOUT"}]

    kept = SearchService._rankable_graph_hits(graph, es, [])

    assert [h["edge"]["document_id"] for h in kept] == ["DOC-CLOSEOUT", "DOC-BULLETIN"]


async def test_graph_outage_degrades_to_primary_asset_scope():
    class DownGraph:
        async def get_asset_knowledge_at(self, asset_id, **kw):
            raise ConnectionError("aura unreachable")

    svc, calls = _service(DownGraph())
    results = await svc.hybrid_search("seal failures", "docs", "EQ-101", 5, False, None, 5)

    assert results == []
    assert calls["es"]["document_ids"] == []


# --- Time-travel (review C8): documents dated after `as_of` leave the text-search arms ------------

class _DocsTable:
    """`documents` rows by id for `corpus.document_rows`; `asset_alias_map` answers empty."""

    def __init__(self, rows):
        self.rows, self.ids, self.name = rows, None, None

    def table(self, name):
        self.name = name
        return self

    def select(self, *_a):
        return self

    def eq(self, *_a):
        return self

    def in_(self, _col, ids):
        self.ids = ids
        return self

    def execute(self):
        from types import SimpleNamespace

        if self.name != "documents":
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[r for r in self.rows if r["document_id"] in (self.ids or [])])


def _dated_service(rows):
    calls = {}
    es_hits = [{"document_id": d, "score": 1.0} for d in ("DOC-OLD", "DOC-NEW", "DOC-UNDATED")]
    qdrant_hits = [{"payload": {"document_id": d}, "score": 0.9} for d in ("DOC-OLD", "DOC-NEW", "DOC-UNDATED")]

    class Engine:
        async def search(self, query, **kw):
            calls["es_limit"] = kw["limit"]
            return list(es_hits)

    class Vector:
        async def search(self, collection, vector, **kw):
            calls["qdrant_limit"] = kw["limit"]
            return list(qdrant_hits)

    class LLM:
        async def embed(self, text, task=None):
            return [0.1]

    svc = SearchService.__new__(SearchService)
    svc.engine, svc.vector, svc.graph, svc.llm, svc.supabase = Engine(), Vector(), None, LLM(), _DocsTable(rows)
    return svc, calls


_ROWS = [
    {"document_id": "DOC-OLD", "file_name": "old.pdf", "occurred_at": "2024-06-01T00:00:00+00:00"},
    {"document_id": "DOC-NEW", "file_name": "new.pdf", "occurred_at": "2025-01-15T00:00:00+00:00"},
    {"document_id": "DOC-UNDATED", "file_name": "undated.pdf", "occurred_at": None},
]


async def test_time_travel_drops_documents_dated_after_as_of():
    """A question "as of 2024" could cite a 2025 bulletin: ES and Qdrant ignored `as_of`."""
    from datetime import UTC, datetime

    svc, calls = _dated_service(_ROWS)
    results = await svc.hybrid_search("seal", "docs", None, 5, False, datetime(2024, 12, 31, tzinfo=UTC), 6)

    ids = {r.document_id for r in results}
    assert "DOC-NEW" not in ids
    assert {"DOC-OLD", "DOC-UNDATED"} <= ids  # earlier, and unknown date, both stay
    assert calls == {"es_limit": 18, "qdrant_limit": 18}  # over-fetch so the filter cannot starve


async def test_without_as_of_nothing_is_dropped_by_date_and_no_over_fetch():
    svc, calls = _dated_service(_ROWS)
    results = await svc.hybrid_search("seal", "docs", None, 5, False, None, 6)

    assert {r.document_id for r in results} == {"DOC-OLD", "DOC-NEW", "DOC-UNDATED"}
    assert calls == {"es_limit": 6, "qdrant_limit": 6}


def test_a_date_only_as_of_means_the_end_of_that_day():
    """The Copilot's picker sends YYYY-MM-DD, which parsed to midnight and dropped that day's documents."""
    from datetime import UTC, datetime

    import pytest
    from fastapi import HTTPException

    from api.routers.search import parse_as_of

    assert parse_as_of("2025-01-15") == datetime(2025, 1, 15, 23, 59, 59, 999999, tzinfo=UTC)
    assert parse_as_of("2025-01-15T08:30:00+00:00") == datetime(2025, 1, 15, 8, 30, tzinfo=UTC)
    assert parse_as_of(None) is None and parse_as_of("") is None
    with pytest.raises(HTTPException) as exc:
        parse_as_of("15/01/2025")
    assert exc.value.status_code == 422
