"""
Compliance router — Regulatory compliance gap detection and audit preparation.
Maps facility regulatory framework against current procedures, equipment states,
and inspection records. High-recall by design: errs toward flagging over clearing.
"""


from fastapi import APIRouter, Query

from api.config import settings
from api.dependencies import CurrentUserDep, Neo4jDep, SupabaseDep, site_scope
from api.services.corpus import document_rows

router = APIRouter()

_SEVERITY = {1: "critical", 2: "major"}


def _severity(authority_level: int) -> str:
    return _SEVERITY.get(authority_level, "minor")


# Gap detection — evaluated per (Regulation × applicable Asset) pair.
#
# A clause is *covered* for an asset when that asset has an active, non-superseded
# edge to a Document of the evidence type the clause actually requires
# (`reg.requires_document_type`, seeded in scripts/seed_regulations.py). Three outcomes:
#
#   gap                 no evidence document of the required type exists
#   unverified_evidence the document exists but no human has verified the edge
#   covered             verified evidence exists — not returned as a finding
#
# This replaces an earlier check that asked only "does this asset have any verified
# procedure at all", which ignored the clause entirely and — because nothing but manual
# quarantine promotion ever writes verification_status='verified' — reported every
# (regulation, asset) pair as a gap unconditionally.
#
# ponytail: `applies_to_equipment_class IS NULL` = clause applies to all equipment classes;
# `requires_document_type IS NULL` (pre-mapping seeds) = any document type counts, which
# keeps older graphs working instead of reporting a false gap on every clause.
# Evidence typing is exact document_type matching. Upgrade to embedding the clause's
# requirement_text against document chunks when clauses need finer granularity than type.
# `CALL { WITH reg, a ... }` is the pre-2025 subquery form. The modern `CALL (reg, a) { ... }`
# needs Neo4j 2025.01+, and the local-stores profile pins neo4j:5.20-community — this form
# runs on both 5.20 and Aura. Switch when the 5.20 pin moves.
_EVIDENCE_MATCH = """
  OPTIONAL MATCH (a)-[r:KNOWLEDGE_EDGE]->(d:Document)
  WHERE (r.valid_to IS NULL OR datetime(r.valid_to) > datetime())
    AND r.verification_status <> 'superseded'
    AND (reg.requires_document_type IS NULL
         OR d.document_type IN reg.requires_document_type)
  RETURN count(DISTINCT d) AS evidence_count,
         count(DISTINCT CASE WHEN r.verification_status = 'verified' THEN d END) AS verified_count
"""

_APPLICABILITY = """
WHERE (reg.applies_to_equipment_class IS NULL
    OR a.equipment_class = reg.applies_to_equipment_class
    OR a.equipment_class CONTAINS reg.applies_to_equipment_class
    OR reg.applies_to_equipment_class CONTAINS a.equipment_class)
"""

_GAP_CYPHER = f"""
MATCH (reg:Concept {{type: 'Regulation'}})
WHERE ($framework IS NULL OR reg.framework = $framework)
MATCH (a:Asset)
{_APPLICABILITY}
  AND ($asset_id IS NULL OR a.asset_id = $asset_id)
  AND ($site_id IS NULL OR a.site_id = $site_id)
CALL {{
  WITH reg, a
  {_EVIDENCE_MATCH}
}}
WITH reg, a, evidence_count, verified_count
WHERE evidence_count = 0 OR verified_count = 0
RETURN reg.concept_id AS concept_id,
       reg.framework AS framework,
       reg.clause_id AS clause_id,
       reg.requirement_text AS requirement_text,
       reg.applies_to_equipment_class AS applies_to,
       reg.requires_document_type AS requires_document_type,
       reg.authority_level AS authority_level,
       a.asset_id AS asset_id,
       a.tag_number AS tag_number,
       a.equipment_class AS equipment_class,
       a.site_id AS site_id,
       evidence_count,
       verified_count,
       CASE WHEN evidence_count = 0 THEN 'gap' ELSE 'unverified_evidence' END AS status
ORDER BY authority_level ASC, asset_id ASC
LIMIT $limit
"""

# Deliberately unbounded: this is an aggregate: a LIMIT would cap the groups returned,
# not the work done, and would silently undercount a compliance posture — worse than a
# slow query. ponytail: O(regulations × applicable assets) with a subquery per pair, fine
# at demo scale (12 clauses × 10 assets). Materialise counts into Supabase on a scheduled
# scan when the asset count reaches the thousands.
_DASHBOARD_CYPHER = f"""
MATCH (reg:Concept {{type: 'Regulation'}})
MATCH (a:Asset)
{_APPLICABILITY}
  AND ($site_id IS NULL OR a.site_id = $site_id)
CALL {{
  WITH reg, a
  {_EVIDENCE_MATCH}
}}
WITH reg, a, evidence_count, verified_count
WHERE evidence_count = 0 OR verified_count = 0
RETURN reg.authority_level AS authority_level,
       reg.framework AS framework,
       reg.applies_to_equipment_class AS equipment_class,
       CASE WHEN evidence_count = 0 THEN 'gap' ELSE 'unverified_evidence' END AS status,
       count(*) AS gap_count
ORDER BY authority_level ASC
"""

# Audit evidence per clause. Evidence must be of the type the clause requires and must sit
# on an asset the clause actually applies to — previously any document on any applicable
# asset counted as evidence for every clause, so the pack could not be wrong.
_AUDIT_CYPHER = """
MATCH (reg:Concept {type: 'Regulation', framework: $framework})
WHERE ($clauses IS NULL OR reg.clause_id IN $clauses)
OPTIONAL MATCH (a:Asset)
WHERE reg.applies_to_equipment_class IS NULL
    OR a.equipment_class = reg.applies_to_equipment_class
    OR a.equipment_class CONTAINS reg.applies_to_equipment_class
    OR reg.applies_to_equipment_class CONTAINS a.equipment_class
OPTIONAL MATCH (a)-[r:KNOWLEDGE_EDGE]->(d:Document)
WHERE (r.valid_to IS NULL OR datetime(r.valid_to) > datetime())
  AND r.verification_status <> 'superseded'
  AND (reg.requires_document_type IS NULL
       OR d.document_type IN reg.requires_document_type)
WITH reg, collect(DISTINCT CASE WHEN d IS NOT NULL THEN {
    document_id: d.document_id,
    document_type: d.document_type,
    asset_id: a.asset_id,
    confidence: r.confidence,
    verification_status: r.verification_status
} END) AS raw_evidence
RETURN reg.clause_id AS clause_id,
       reg.requirement_text AS requirement_text,
       reg.applies_to_equipment_class AS applies_to,
       reg.requires_document_type AS requires_document_type,
       reg.authority_level AS authority_level,
       [e IN raw_evidence WHERE e IS NOT NULL] AS evidence
ORDER BY reg.clause_id ASC
"""


def _dedupe_evidence(evidence: list[dict]) -> list[dict]:
    """One audit-evidence entry per document.

    `_AUDIT_CYPHER` collects DISTINCT over the whole map, which carries the linked asset and the edge's
    confidence and verification status — so a procedure covering HE-301/302/303, or a document linked
    by several edges, was listed once per link. The pack showed the same file repeatedly and
    `total_evidence_docs` counted links, not documents. A document is verified if any link is.
    """
    merged: dict[str, dict] = {}
    for item in evidence:
        doc_id = item.get("document_id")
        if not doc_id:
            continue
        asset = item.get("asset_id")
        if doc_id not in merged:
            merged[doc_id] = {**item, "asset_ids": [asset] if asset else []}
            continue
        kept = merged[doc_id]
        if asset and asset not in kept["asset_ids"]:
            kept["asset_ids"].append(asset)
        if item.get("verification_status") == "verified":
            kept["verification_status"] = "verified"
        kept["confidence"] = max(kept.get("confidence") or 0, item.get("confidence") or 0)
    return list(merged.values())


@router.get("/gaps", summary="List detected compliance gaps")
async def list_compliance_gaps(
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    framework: str | None = Query(None, description="Regulatory framework: OISD_117, ISO_45001, etc."),
    asset_id: str | None = Query(None),
    site_id: str | None = Query(None),
    severity: str | None = Query(None, description="critical, major, minor"),
    status: str | None = Query(None, description="gap (no evidence) or unverified_evidence"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
) -> dict:
    """
    Detects findings per (clause × applicable asset): `gap` when no document of the
    evidence type the clause requires is linked to the asset, `unverified_evidence`
    when one exists but no human has verified the edge.

    High-recall by intent — errs toward flagging — but the finding is now tied to the
    specific clause requirement, so a cleared clause is genuinely cleared.
    Never auto-clears safety-critical.
    """
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = await session.run(
            _GAP_CYPHER,
            framework=framework,
            asset_id=asset_id,
            site_id=site_scope(current_user, site_id),
            limit=limit,
        )
        rows = [dict(r) async for r in result]

    items = [
        {**r, "severity": _severity(r["authority_level"])}
        for r in rows
        if (severity is None or _severity(r["authority_level"]) == severity)
        and (status is None or r["status"] == status)
    ]

    return {
        "items": items,
        "total": len(items),
        "gap_total": sum(1 for i in items if i["status"] == "gap"),
        "unverified_total": sum(1 for i in items if i["status"] == "unverified_evidence"),
        "limit": limit,
        "offset": offset,
        "framework": framework,
        "last_scan": "realtime",
    }


@router.get("/dashboard", summary="Compliance posture dashboard")
async def compliance_dashboard(
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    site_id: str | None = Query(None),
) -> dict:
    """
    Aggregated compliance gap counts by severity, framework, and equipment class.
    Designed for Quality Managers and Compliance Officers.
    """
    site_id = site_scope(current_user, site_id)
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = await session.run(_DASHBOARD_CYPHER, site_id=site_id)
        rows = [dict(r) async for r in result]

    totals = {"critical": 0, "major": 0, "minor": 0}
    unverified_totals = {"critical": 0, "major": 0, "minor": 0}
    by_framework: dict = {}
    by_asset_class: dict = {}

    for r in rows:
        sev = _severity(r["authority_level"])
        count = r["gap_count"]

        # total_gaps counts only true gaps (no evidence of the required type). Findings
        # where evidence exists but is unverified are reported separately — conflating the
        # two is what made every clause look non-compliant.
        if r["status"] == "gap":
            totals[sev] = totals.get(sev, 0) + count
        else:
            unverified_totals[sev] = unverified_totals.get(sev, 0) + count
            continue

        fw = r["framework"] or "unknown"
        by_framework.setdefault(fw, {"critical": 0, "major": 0, "minor": 0})
        by_framework[fw][sev] = by_framework[fw].get(sev, 0) + count

        cls = r["equipment_class"] or "all"
        by_asset_class.setdefault(cls, {"critical": 0, "major": 0, "minor": 0})
        by_asset_class[cls][sev] = by_asset_class[cls].get(sev, 0) + count

    return {
        "site_id": site_id,
        "total_gaps": totals,
        "total_unverified_evidence": unverified_totals,
        "by_framework": by_framework,
        "by_asset_class": by_asset_class,
        "last_updated": "realtime",
    }


@router.get("/audit-pack", summary="Generate audit evidence package")
async def generate_audit_pack(
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    supabase: SupabaseDep,
    framework: str = Query(..., description="Target regulatory framework, e.g. OISD_117"),
    clauses: list[str] | None = Query(None, description="Specific clause IDs; omit for all clauses in framework"),
) -> dict:
    """
    Assembles evidence package per regulatory clause.
    Clauses with all evidence below confidence 0.7 require human review before clearance.
    Human sign-off is mandatory — this is audit-preparation acceleration, not automated compliance.
    """
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = await session.run(_AUDIT_CYPHER, framework=framework, clauses=clauses)
        rows = [dict(r) async for r in result]
    for r in rows:
        r["evidence"] = _dedupe_evidence(r.get("evidence") or [])

    human_review_required = []
    assembled = []

    # An auditor reads evidence by name, so attach the vault file name (a promoted field input has no
    # vault document and is labelled as what it is). The pack used to list bare document ids.
    all_ids = [e.get("document_id") for r in rows for e in (r.get("evidence") or []) if e.get("document_id")]
    file_names = {d["document_id"]: d.get("file_name") for d in await document_rows(supabase, all_ids)}
    for r in rows:
        for e in r.get("evidence") or []:
            doc_id = e.get("document_id") or ""
            e["title"] = file_names.get(doc_id) or (
                "Promoted field input" if doc_id.startswith("PROMOTED-") else doc_id
            )

    for r in rows:
        evidence = r.get("evidence") or []
        verified = [e for e in evidence if e.get("verification_status") == "verified"]
        low_confidence = all(e.get("confidence", 0) < 0.7 for e in evidence) if evidence else True

        clause_entry = {
            "clause_id": r["clause_id"],
            "requirement_text": r["requirement_text"],
            "applies_to": r["applies_to"],
            "authority_level": r["authority_level"],
            "severity": _severity(r["authority_level"]),
            "evidence": evidence,
            "verified_evidence_count": len(verified),
            "clearance_blocked": low_confidence,
        }
        assembled.append(clause_entry)
        if low_confidence:
            human_review_required.append(r["clause_id"])

    total_docs = sum(len(c["evidence"]) for c in assembled)

    return {
        "framework": framework,
        "clauses": assembled,
        "total_clauses": len(assembled),
        "total_evidence_docs": total_docs,
        "human_review_required": human_review_required,
        "note": "Human sign-off required for all clearances. This package is audit-preparation only.",
        "status": "draft",
    }


@router.get("/frameworks", summary="List configured regulatory frameworks")
async def list_frameworks(
    current_user: CurrentUserDep,
    driver: Neo4jDep,
) -> dict:
    """Returns frameworks present in the Neo4j knowledge graph (i.e. already seeded)."""
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = await session.run(
            "MATCH (c:Concept {type: 'Regulation'}) RETURN DISTINCT c.framework AS framework ORDER BY framework"
        )
        seeded = [r["framework"] async for r in result]

    return {
        "configured_frameworks": seeded,
        "available_frameworks": [
            "OISD_117", "PESO", "FDA_21CFR_PART11", "CEA", "IEC_62443",
            "ISO_45001", "ISO_22000", "FSSAI", "SCHEDULE_M",
        ],
    }
