"""
Service-free tests for `api/services/corpus.py` — the test-artifact predicate shared by
`GET /assets/{id}/knowledge` and `benchmark/run_kg_completeness.py`.

The dangerous direction here is OVER-matching. This filter never deletes anything, but a
pattern that swallows a real corpus file name makes genuine evidence invisible in the graph
view, and an invisible fact is indistinguishable from an absent one. The real corpus names are
pinned below so widening the regex fails loudly.
"""

import pytest

from api.services.corpus import (
    REAL_ASSET_CYPHER,
    TEST_ASSET_PREFIXES,
    is_test_artifact,
    partition_test_artifacts,
)

# Every real name in the golden corpus that the filter must NEVER match. Taken from the live
# vault on 2026-08-23 (23 active corpus documents).
REAL_CORPUS_NAMES = [
    "sop_he_301_isolation.pdf",
    "oem_manual_eq1xx_seal.pdf",
    "oem_bulletin_fp_sb_2025_04.pdf",
    "insp_v247_2025_11.pdf",
    "ptw_v247.pdf",
    "pid_line3_isolation_boundary.png",
    "shift_log.txt",
    "work_order_closeout_form.pdf",
    "work_orders_eq101_family.csv",
    "regulatory_clause_excerpts.pdf",
    "handwritten_shift_log.png",
    "scanned_inspection_degraded.png",
]

# Names the suite and hand-run sweeps actually wrote, observed live in the vault.
TEST_ARTIFACT_NAMES = [
    "ann_test_1252F91A.txt",
    "dbtest_01869BC0.txt",
    "test_04F1EF6B.txt",
    "probe_scratch.txt",
    "tmp_upload.txt",
    "# Kairos scratch.md",
    # Added by decision D8 (2026-08-23). Both name a file after this system or its harness,
    # never after plant equipment; neither appears in dataset_manifest.csv.
    "e2e_shift_log.txt",
    "kairos_ingest_test.pdf",
]


@pytest.mark.parametrize("name", REAL_CORPUS_NAMES)
def test_real_corpus_documents_are_never_filtered(name):
    assert is_test_artifact(name) is False, (
        f"{name!r} is real corpus evidence. Matching it here hides it from the graph view, "
        "which is the one failure mode this filter must not have."
    )


@pytest.mark.parametrize("name", TEST_ARTIFACT_NAMES)
def test_known_test_artifacts_are_filtered(name):
    assert is_test_artifact(name) is True


def test_matches_are_anchored_at_the_start():
    """`test_` mid-name is a real word, not a prefix — `pressure_test_report.pdf` is evidence."""
    assert is_test_artifact("pressure_test_report.pdf") is False
    assert is_test_artifact("insp_dbtest_note.pdf") is False


@pytest.mark.parametrize("name", ["hydro_test.pdf", "pressure_test.pdf", "insp_he301_test.pdf"])
def test_a_test_stem_does_not_make_a_document_an_artifact(name):
    """D8 rejected a `_test.ext` stem rule for exactly these. A hydrostatic test report is plant
    evidence; matching it would hide real knowledge, which is worse than leaving noise visible."""
    assert is_test_artifact(name) is False


def test_case_is_ignored():
    assert is_test_artifact("TEST_ABC.txt") is True
    assert is_test_artifact("DBTest_01.txt") is True


def test_missing_or_empty_file_name_is_not_an_artifact():
    """Unclassifiable is not disposable — see the module docstring."""
    assert is_test_artifact(None) is False
    assert is_test_artifact("") is False


def test_partition_returns_only_matching_ids():
    rows = [
        {"document_id": "DOC-REAL", "file_name": "ptw_v247.pdf"},
        {"document_id": "DOC-FAKE", "file_name": "test_9B4CB0DA.txt"},
        {"document_id": "DOC-NONAME", "file_name": None},
    ]
    assert partition_test_artifacts(rows) == {"DOC-FAKE"}


def test_partition_skips_rows_without_an_id():
    rows = [{"file_name": "test_abc.txt"}, {"document_id": "", "file_name": "test_def.txt"}]
    assert partition_test_artifacts(rows) == set()


def test_promoted_ids_are_never_classifiable_as_artifacts():
    """`PROMOTED-<uuid>` has no vault row at all, so it can never appear in a lookup result —
    which is exactly why an id absent from `documents` must be kept, not dropped."""
    rows = [{"document_id": "PROMOTED-f17b1416", "file_name": None}]
    assert partition_test_artifacts(rows) == set()


# --- test assets --------------------------------------------------------------------
# The same over-matching risk, for assets: a prefix that swallows a real tag hides the asset from
# the list, the compliance posture and the coverage matrix at once. The golden registry is pinned
# so widening TEST_ASSET_PREFIXES fails loudly.
REAL_ASSET_IDS = ["EQ-101", "EQ-102", "EQ-103", "V-247", "XV-203", "XV-204", "PG-18",
                  "HE-301", "HE-302", "HE-303"]  # dataset/01_Structured_Backbone/asset_registry.csv


@pytest.mark.parametrize("asset_id", REAL_ASSET_IDS)
def test_no_real_asset_matches_a_test_prefix(asset_id):
    assert not asset_id.startswith(TEST_ASSET_PREFIXES)


def test_the_qa_sweep_asset_is_a_test_asset():
    assert "QA-TEST-155635".startswith(TEST_ASSET_PREFIXES)


def test_a_quality_tag_that_merely_starts_with_qa_is_kept():
    """`QA-` alone could be a real quality-assurance tag; only `QA-TEST-` names a test."""
    assert not "QA-101".startswith(TEST_ASSET_PREFIXES)


def test_every_compliance_query_that_lists_assets_carries_the_guard():
    from api.routers import compliance

    for name in ("_GAP_CYPHER", "_DASHBOARD_CYPHER", "_AUDIT_CYPHER"):
        assert REAL_ASSET_CYPHER in getattr(compliance, name), name


async def test_asset_list_filters_in_the_query_and_reports_what_it_hid():
    """Filtering after a paginated query would break `total`; the guard must be in the Cypher,
    and the count must say how many test assets were hidden."""
    from api.services.graph import GraphService

    seen: list[str] = []

    class _Result:
        def __init__(self, cypher):
            self._cypher = cypher

        async def single(self):
            return {"total": 10, "excluded": 1}

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def run(self, cypher, **params):
            seen.append(cypher)
            return _Result(cypher)

    class _Driver:
        def session(self, **kwargs):
            return _Session()

    result = await GraphService(_Driver()).list_assets()

    list_cypher = next(c for c in seen if "SKIP" in c)
    count_cypher = next(c for c in seen if "excluded" in c)
    assert REAL_ASSET_CYPHER in list_cypher
    assert "NOT " + REAL_ASSET_CYPHER in count_cypher
    assert result["total"] == 10 and result["excluded_test_assets"] == 1


async def test_excluded_count_uses_the_negated_guard_and_the_site_scope():
    from api.services.corpus import excluded_test_asset_count

    seen = {}

    class _Result:
        async def single(self):
            return {"n": 3}

    class _Session:
        async def run(self, cypher, **params):
            seen["cypher"], seen["params"] = cypher, params
            return _Result()

    assert await excluded_test_asset_count(_Session(), "SITE_001") == 3
    assert "NOT " + REAL_ASSET_CYPHER in seen["cypher"]
    assert seen["params"] == {"site_id": "SITE_001", "hide_demo": True}
