"""
Corpus hygiene — telling real vault documents apart from test artifacts.

WHY THIS EXISTS
  The test suite and hand-run sweeps write real rows into the vault. They carry ordinary random
  `DOC-` ids, so **only the file name identifies them**. On 2026-08-23 the active vault held 23
  real corpus documents against 85 test artifacts — 79% noise — and anything that counts or
  renders documents without excluding them is reporting test hygiene rather than the plant.

  `benchmark/run_kg_completeness.py` hit this first: linkage read 70/108 = 64% until the
  artifacts left the denominator, at which point the real figure was 18/23. The harness was
  fixed; every user-facing surface was not, which is why `GET /assets/{id}/knowledge` returned
  60 edges for EQ-101 of which ~53 pointed at `test_*` files.

  This module is the single definition. The benchmark imports it rather than keeping its own
  copy — `benchmark/` already depends on `api/`, so the direction is api → benchmark and never
  the reverse.

WHAT IS DELIBERATELY NOT EXCLUDED
  A `document_id` with **no vault row at all** is never treated as a test artifact. Promotion
  from quarantine mints `PROMOTED-<uuid>` ids for field knowledge that never had a vault
  document (`routers/governance.py`), so "not in `documents`" means "cannot classify", and the
  conservative answer is to keep it. Over-widening this predicate deletes real evidence from a
  view; under-widening merely leaves noise visible.

NEVER SILENTLY
  Callers are expected to report how many they excluded. A filter that hides its own effect is
  precisely how the linkage number was wrong for as long as it was.
"""

import asyncio
import re
from collections.abc import Collection, Iterable

import structlog

log = structlog.get_logger(__name__)

# Documents written by the test suite and by hand during sweeps. Anchored at the start of the
# file name. `# Kairos` catches scratch files saved straight from a markdown heading.
#
# `e2e_` and `kairos_` were added 2026-08-23 (decision D8). Both name a file after *this system*
# or its test harness, never after plant equipment, and both were verified against the whole
# vault to match exactly their two targets — `e2e_shift_log.txt` and `kairos_ingest_test.pdf` —
# neither of which appears in `dataset/00_Reference/dataset_manifest.csv` or anywhere under
# `dataset/`. A `_test\.ext` stem rule was considered for the second and REJECTED: it would also
# swallow a plausible real document like `hydro_test.pdf`, and hiding plant evidence is the one
# failure this predicate must not have.
#
# Widen this ONLY with evidence: `backend/scripts/purge_test_data.py` has destroyed real
# documents once by widening a match pattern, and while this module deletes nothing, a pattern
# that swallows a real file name makes genuine evidence invisible in the UI, which is its own
# kind of data loss.
# `linked-doc-` is the integration suite's document-linking fixture (`source_system=integration_test`);
# it reached the Documents list and EQ-101's knowledge panel before being added here.
_TEST_FILENAME = re.compile(r"^(ann_test_|dbtest_|test_|e2e_|kairos_|probe|tmp|linked-doc-|# Kairos)", re.I)

# Supabase/PostgREST puts every `.in_()` value in the URL, so a huge list becomes an over-long
# query string. Asset knowledge graphs are bounded (60 edges on the largest corpus asset), but
# chunking keeps this safe for any caller.
_LOOKUP_CHUNK = 200


def is_test_artifact(file_name: str | None) -> bool:
    """True when a vault file name identifies a test/sweep artifact rather than corpus evidence."""
    return bool(_TEST_FILENAME.match(file_name or ""))


def partition_test_artifacts(rows: Iterable[dict]) -> set[str]:
    """Given `documents` rows (needing `document_id` + `file_name`), return the test-artifact ids."""
    return {
        r["document_id"]
        for r in rows
        if r.get("document_id") and is_test_artifact(r.get("file_name"))
    }


async def test_artifact_ids(supabase, document_ids: Collection[str]) -> set[str]:
    """Resolve which of `document_ids` are test artifacts, by looking their file names up in the vault.

    Read-only. Ids absent from `documents` are **not** returned — see the module docstring: an
    unresolvable id is unclassifiable, not disposable.

    On a lookup failure this returns an empty set, so the caller shows everything rather than
    silently hiding evidence because Supabase was unreachable. Failing open is the correct
    direction here: the cost is visible noise, where failing closed would blank a real graph.
    """
    return partition_test_artifacts(await document_rows(supabase, document_ids))


async def document_rows(supabase, document_ids: Collection[str]) -> list[dict]:
    """`documents` rows (`document_id`, `file_name`) for the given ids, chunked.

    Shared by the test-artifact filter and by callers that need a readable source name, so one
    lookup serves both. Returns `[]` on any failure — callers fail open (see `test_artifact_ids`).
    """
    ids = [d for d in dict.fromkeys(document_ids) if d]
    rows: list[dict] = []
    for start in range(0, len(ids), _LOOKUP_CHUNK):
        chunk = ids[start : start + _LOOKUP_CHUNK]
        try:
            res = await asyncio.to_thread(
                lambda c=chunk: supabase.table("documents")
                .select("document_id, file_name")
                .in_("document_id", c)
                .execute()
            )
            rows.extend(res.data or [])
        except Exception as exc:  # noqa: BLE001 — a hygiene filter must never fail a read
            log.warning("corpus.test_artifact_lookup_failed", error=str(exc), chunk_size=len(chunk))
            return []
    return rows
