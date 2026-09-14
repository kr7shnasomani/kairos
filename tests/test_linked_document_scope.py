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
        async def search(self, index, body):
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

    # Authority still leads; within level 5 the asset's own document wins the last slot.
    assert [x.document_id for x in out] == ["DOC-SOP", "DOC-CLOSEOUT"]


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
