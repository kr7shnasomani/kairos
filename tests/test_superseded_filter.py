"""Superseded documents must not surface as current (ARCHITECTURE.md §8).

Pure logic: fake ES / Qdrant clients capture the query that would be sent, so no services
are required. What is asserted is the *shape of the filter*, which is the thing that breaks.
"""

from typing import Any

import pytest

from api.services.search_engine import SearchEngineService
from api.services.vector_store import VectorStoreService

_SUPERSEDED_TERM = {"term": {"status": "superseded"}}


class _FakeES:
    """Captures the search body and returns no hits."""

    def __init__(self) -> None:
        self.body: dict[str, Any] = {}

    async def search(self, index: str, body: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        self.body = body
        return {"hits": {"hits": []}}


class _FakeQdrant:
    def __init__(self) -> None:
        self.query_filter: Any = None
        self.set_payload_args: dict[str, Any] = {}

    async def search(self, collection_name, query_vector, query_filter, limit, with_payload):
        self.query_filter = query_filter
        return []

    async def set_payload(self, collection_name, payload, points):
        self.set_payload_args = {"collection": collection_name, "payload": payload, "points": points}


class _Settings:
    ELASTICSEARCH_INDEX_DOCUMENTS = "kairos_documents"
    ELASTICSEARCH_INDEX_ASSETS = "kairos_assets"
    QDRANT_COLLECTION_DOCUMENTS = "kairos_documents"


def _must_not(body: dict[str, Any]) -> list:
    return body.get("query", {}).get("bool", {}).get("must_not", [])


# ── Elasticsearch ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_es_excludes_superseded_by_default():
    es = _FakeES()
    await SearchEngineService(es, _Settings()).search("MAWP for HE-301")
    assert _SUPERSEDED_TERM in _must_not(es.body)


@pytest.mark.asyncio
async def test_es_includes_superseded_for_time_travel():
    """A document superseded today was current at an earlier as_of — excluding it there
    answers the wrong question."""
    es = _FakeES()
    await SearchEngineService(es, _Settings()).search("MAWP for HE-301", include_superseded=True)
    assert _SUPERSEDED_TERM not in _must_not(es.body)


@pytest.mark.asyncio
async def test_es_uses_must_not_never_must_active():
    """
    The query spans kairos_assets too, whose documents carry no `status` field. Requiring
    status=active would drop every asset hit; excluding superseded leaves them alone.
    """
    es = _FakeES()
    await SearchEngineService(es, _Settings()).search("P-101")
    must = es.body["query"]["bool"]["must"]
    assert not any("status" in str(clause) for clause in must), must


# ── Qdrant ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_qdrant_excludes_superseded_by_default():
    q = _FakeQdrant()
    await VectorStoreService(q, _Settings()).search("kairos_documents", [0.1, 0.2])
    keys = [c.key for c in (q.query_filter.must_not or [])]
    assert "status" in keys


@pytest.mark.asyncio
async def test_qdrant_includes_superseded_for_time_travel():
    q = _FakeQdrant()
    await VectorStoreService(q, _Settings()).search(
        "kairos_documents", [0.1, 0.2], include_superseded=True
    )
    assert not (q.query_filter.must_not or [])


@pytest.mark.asyncio
async def test_qdrant_filter_survives_with_no_must_conditions():
    """
    Regression: the filter used to be `Filter(must=...) if must else None`. With no asset_id
    and quarantine already excluded there can still be a must_not, and returning None there
    would silently drop the superseded exclusion.
    """
    q = _FakeQdrant()
    await VectorStoreService(q, _Settings()).search(
        "kairos_documents", [0.1, 0.2], include_quarantine=True
    )
    assert q.query_filter is not None, "must_not alone must still produce a filter"


@pytest.mark.asyncio
async def test_mark_superseded_sets_payload_and_never_deletes():
    q = _FakeQdrant()
    await VectorStoreService(q, _Settings()).mark_superseded("kairos_documents", "DOC-1")
    assert q.set_payload_args["payload"] == {"status": "superseded"}
    assert q.set_payload_args["points"].must[0].key == "document_id"


# =============================================================================
# Layer 7 — pending-MoC disclosure reaches every output type
# =============================================================================


class _MocQuery:
    def __init__(self, table, data):
        self._table, self._data = table, data

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a):
        return self

    def in_(self, *_a):
        return self

    def execute(self):
        class _R:
            pass

        r = _R()
        r.data = self._data
        return r


class _MocSupabase:
    """Two-table stand-in: knowledge_conflicts + moc_items."""

    def __init__(self, conflicts, mocs):
        self._c, self._m = conflicts, mocs

    def table(self, name):
        return _MocQuery(name, self._c if name == "knowledge_conflicts" else self._m)


async def test_pending_moc_warning_is_raised_for_a_cited_asset():
    from api.routers.search import pending_moc_warnings

    sb = _MocSupabase(
        conflicts=[{
            "conflict_id": "C-1", "asset_id": "EQ-101", "parameter": "seal_torque",
            "severity": "major", "sla_deadline": "2026-08-20T00:00:00Z",
        }],
        mocs=[{"moc_id": "MOC-9", "conflict_id": "C-1", "status": "pending"}],
    )
    out = await pending_moc_warnings(sb, [{"asset_id": "EQ-101"}])

    assert len(out) == 1
    assert out[0]["asset_id"] == "EQ-101"
    assert out[0]["parameter"] == "seal_torque"


async def test_no_warning_when_no_asset_is_cited():
    from api.routers.search import pending_moc_warnings

    sb = _MocSupabase(conflicts=[{"conflict_id": "C-1", "asset_id": "EQ-101"}], mocs=[])
    assert await pending_moc_warnings(sb, [{"title": "no asset here"}]) == []


async def test_lookup_failure_does_not_take_the_answer_down():
    from api.routers.search import pending_moc_warnings

    class _Broken:
        def table(self, _n):
            raise RuntimeError("supabase down")

    assert await pending_moc_warnings(_Broken(), [{"asset_id": "EQ-101"}]) == []


def test_every_answer_surface_can_carry_the_moc_banner():
    """Regression: the banner reached synthesized answers only, so the same asset under the same
    pending change was flagged in the copilot and silent in search and the RCA pack."""
    from api.models.document import RCAPackResponse, SearchResponse, SynthesizeResponse

    for model in (SearchResponse, RCAPackResponse, SynthesizeResponse):
        assert "pending_moc" in model.model_fields, f"{model.__name__} cannot disclose a pending MoC"
