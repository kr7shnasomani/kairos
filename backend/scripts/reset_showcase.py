"""
Put the showcase plant's STATE back to its seed: what visitors changed in the demo, undone.

The demo is shared and every action works, so visitors will leave it messy (resolved conflicts, promoted
or disputed items, acknowledged briefs, events they raised). This deletes the showcase's state rows and
writes the seed again. It is the only code path that deletes, so it is narrow on purpose:

  * Every delete is a marker filter from `MARKERS` below (a `DEMO-` asset or person id, or a showcase
    site) and nothing else. There is no unfiltered delete and no filter built from user input.
    `tests/test_showcase_dataset.py` fails if a delete could match a row without a marker.
  * It deletes STATE only: events, briefs, conflicts, MoC, quarantine, knowledge capture, plant states, and
    the unconfirmed alias guesses the pipeline made for showcase assets, and the graph edges a showcase
    document wrongly put on a real asset (never an edge of a real document).
    It never touches the vault (documents, their jobs and files stay: the vault is permanent), assets,
    or any real row (a stray edge sits on a real asset but belongs to a showcase document).
  * Facts a visitor promoted into the graph stay: the temporal graph supersedes, it does not delete.
  * Dry run by default. `--apply` also needs SHOWCASE_CONFIRM=reset-showcase-state.

    python scripts/reset_showcase.py            # dry run: prints what it would delete, per table
    SHOWCASE_CONFIRM=reset-showcase-state python scripts/reset_showcase.py --apply
"""

import argparse
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, "/app")

import structlog
from supabase import create_client

from api.config import Settings
from api.services import tenant
from scripts.showcase import files

log = structlog.get_logger(__name__)

CONFIRM = "reset-showcase-state"
LIKE = f"{tenant.DEMO_PREFIX}*"
SITES = list(tenant.DEMO_SITES)

# (table, column, kind). Delete order is dependency order: children before parents.
MARKERS: tuple[tuple[str, str, str], ...] = (
    ("moc_items", "asset_id", "prefix"),
    ("quarantine_items", "asset_id", "prefix"),
    ("knowledge_conflicts", "asset_id", "prefix"),
    ("elicitation_sessions", "asset_id", "prefix"),
    ("offboarding_sessions", "personnel_id", "prefix"),  # its items cascade
    ("operational_events", "site_id", "site"),
    ("plant_operating_states", "site_id", "site"),
)
# Briefs are special: a showcase brief is marked by its asset, or (a shift handover has no asset) by being
# addressed to a showcase site or to the demo account. Feedback on them goes first.


def marked(query, kind: str, column: str):
    """Restrict `query` to showcase rows. Only ever called with a column from MARKERS."""
    return query.like(column, LIKE) if kind == "prefix" else query.in_(column, SITES)


def brief_ids(sb) -> list[str]:
    ids: set[str] = set()
    for q in (
        sb.table("briefs").select("brief_id").like("asset_id", LIKE),
        sb.table("briefs").select("brief_id").in_("recipient_user_id", [f"site-{s}" for s in SITES]),
    ):
        ids |= {r["brief_id"] for r in (q.execute().data or [])}
    demo_ids = tenant_demo_ids(sb)
    if demo_ids:
        ids |= {r["brief_id"] for r in (sb.table("briefs").select("brief_id, asset_id").in_("recipient_user_id", demo_ids).execute().data or [])
                if r["asset_id"] is None or tenant.is_demo_id(r["asset_id"])}
    return sorted(ids)


def tenant_demo_ids(sb) -> list[str]:
    import asyncio

    tenant._demo_ids = (0.0, [])  # always ask Auth fresh before a delete
    return asyncio.run(tenant.demo_user_ids(sb))


def candidates(query):
    """Restrict `query` to alias candidates the extraction pipeline proposed for a showcase asset and nobody
    confirmed: the guesses a document leaves behind. The dataset's own candidates have another source and a
    confirmed alias is never matched."""
    return query.like("canonical_asset_id", LIKE).eq("confirmed", False).like("alias_source", "ner_extraction:*")


def plan(sb) -> dict[str, int]:
    """How many rows each delete would remove."""
    counts: dict[str, int] = {"brief_feedback": 0, "briefs": 0}
    ids = brief_ids(sb)
    counts["briefs"] = len(ids)
    for i in range(0, len(ids), 100):
        counts["brief_feedback"] += sb.table("brief_feedback").select("id", count="exact").in_("brief_id", ids[i:i + 100]).limit(1).execute().count or 0
    for table, column, kind in MARKERS:
        counts[table] = marked(sb.table(table).select(column, count="exact").limit(1), kind, column).execute().count or 0
    counts["asset_alias_map"] = candidates(sb.table("asset_alias_map").select("alias", count="exact").limit(1)).execute().count or 0
    return counts


def delete_state(sb) -> dict[str, int]:
    done = plan(sb)
    ids = brief_ids(sb)
    for i in range(0, len(ids), 100):
        sb.table("brief_feedback").delete().in_("brief_id", ids[i:i + 100]).execute()
        sb.table("briefs").delete().in_("brief_id", ids[i:i + 100]).execute()
    for table, column, kind in MARKERS:
        marked(sb.table(table).delete(), kind, column).execute()
        log.info("showcase.reset_deleted", table=table, rows=done[table])
    candidates(sb.table("asset_alias_map").delete()).execute()
    log.info("showcase.reset_deleted", table="asset_alias_map", rows=done["asset_alias_map"])
    return done


# Edges a showcase document put on a REAL asset: the extractor named an asset the page did not (EQ-101, its own
# prompt example), before the pipeline refused such links (`tenant.link_allowed`). The marker is two-sided: the
# edge cites a showcase document and its asset is not a showcase asset. A real document's edge never matches.
STRAY_EDGES = "MATCH (a:Asset)-[k:KNOWLEDGE_EDGE]->() WHERE k.document_id IN $ids AND NOT a.asset_id STARTS WITH $prefix"


def showcase_document_ids(sb) -> list[str]:
    ids: list[str] = []
    for offset in range(0, 100000, 1000):
        rows = sb.table("documents").select("document_id, access_tags").range(offset, offset + 999).execute().data or []
        ids += [r["document_id"] for r in rows if tenant.is_demo_document(r)]
        if len(rows) < 1000:
            break
    return ids


def stray_edges(settings, ids: list[str], *, delete: bool) -> int:
    """How many stray edges there are (and, with `delete`, remove exactly those)."""
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD))
    try:
        with driver.session(database=settings.NEO4J_DATABASE) as session:
            params = {"ids": ids, "prefix": tenant.DEMO_PREFIX}
            count = session.run(STRAY_EDGES + " RETURN count(k) AS n", **params).single()["n"]
            if delete and count:
                session.run(STRAY_EDGES + " DELETE k", **params).consume()
            return count
    finally:
        driver.close()


def document_ids(sb, docs) -> dict[str, str]:
    rows = sb.table("documents").select("document_id, file_name, access_tags").in_("file_name", [d.file_name for d in docs]).execute().data or []
    return {r["file_name"]: r["document_id"] for r in rows if tenant.is_demo_document(r)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset the showcase plant's state to its seed.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    counts = plan(sb)
    showcase_docs = showcase_document_ids(sb)
    counts["stray_edges_on_real_assets"] = stray_edges(settings, showcase_docs, delete=False)
    print("Would delete (showcase state only):", counts)
    if not args.apply:
        print("Dry run: nothing was deleted. Re-run with --apply and SHOWCASE_CONFIRM to reset.")
        return
    if os.getenv("SHOWCASE_CONFIRM") != CONFIRM:
        raise SystemExit(f"--apply needs SHOWCASE_CONFIRM={CONFIRM}")

    from scripts import load_showcase

    ds = files.read(files.showcase_root())
    demo = tenant_demo_ids(sb)
    if not demo:
        raise SystemExit("no demo account found; the seed briefs need its id")
    anchor = datetime.now(UTC)
    deleted = delete_state(sb)
    deleted["stray_edges_on_real_assets"] = stray_edges(settings, showcase_docs, delete=True)
    sc = files.bind(ds, now=anchor, demo_user_id=demo[0], doc_ids=document_ids(sb, ds.docs))
    load_showcase.write_history(sb, settings, sc)
    load_showcase.materialise_events(settings, sc)
    print("Deleted:", deleted, "and wrote the seed again.")


if __name__ == "__main__":
    main()
