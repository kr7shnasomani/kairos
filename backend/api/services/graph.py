"""
Graph service — Neo4j temporal graph operations (Layer 4).
All write operations enforce the six mandatory edge properties.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from neo4j import AsyncDriver

log = structlog.get_logger(__name__)


# ARCHITECTURE.md §7: "traversal depth limits enforced by query policy". One named bound rather
# than a literal inlined per query, so a new variable-length traversal cannot quietly ship unbounded
# — an unbounded `*` on a temporal graph is the pathological case the section is about.
#
# 10 is deliberately generous: physical plant hierarchies (site → unit → system → equipment → part)
# are 4-6 deep, so this is headroom, not a working limit. It bounds the planner's work, it does not
# shape results. Raise it only with a `PROFILE` showing the deeper plan is still a seek + expand.
MAX_TRAVERSAL_DEPTH = 10

# What the pipeline's provenance edges say about the node at the far end of them.
_ENTITY_TYPE_BY_RELATIONSHIP = {
    "DOCUMENTED_BY": "asset_tag",
    "MENTIONS_PERSON": "person",
    "MENTIONS_ORGANISATION": "organisation",
    "CONTAINS_TOPOLOGY_ELEMENT": "topology_element",
}


def entities_from_edges(document_id: str, affected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn `get_blast_radius` rows into the extracted entities they record, one per value.

    Each row is an edge carrying this document's id; the entity is whichever endpoint is not the
    document itself (an Asset for `DOCUMENTED_BY`, a Person for `MENTIONS_PERSON`, ...).
    """
    entities: dict[tuple[str, str], dict[str, Any]] = {}
    for row in affected:
        edge = row.get("edge") or {}
        source, target = row.get("source") or {}, row.get("target") or {}
        node = target if source.get("document_id") == document_id else source
        value = node.get("asset_id") or node.get("name") or node.get("tag_number") or node.get("element_id")
        if not value:
            continue
        relationship = str(edge.get("relationship_type") or "")
        entity_type = _ENTITY_TYPE_BY_RELATIONSHIP.get(relationship, relationship.lower() or "fact")
        confidence = min(max(float(edge.get("confidence") or 0.0), 0.0), 1.0)
        key = (entity_type, str(value))
        # Re-runs can link the same entity twice; keep the strongest link.
        if key in entities and entities[key]["confidence"] >= confidence:
            continue
        entities[key] = {
            "entity_type": entity_type,
            "value": str(value),
            "confidence": confidence,
            "linked_asset_id": node.get("asset_id"),
            "requires_review": edge.get("verification_status") != "verified",
        }
    return list(entities.values())


def person_names_from_edges(affected: list[dict[str, Any]]) -> list[str]:
    """Names of the Person nodes a document mentions — the redaction list for its export."""
    names = {
        str((row.get("target") or {}).get("name") or "").strip()
        for row in affected
        if (row.get("edge") or {}).get("relationship_type") == "MENTIONS_PERSON"
    }
    return sorted(n for n in names if n)


class GraphService:
    """
    Service layer for all Neo4j temporal graph operations.
    Enforces: validity windows, authority hierarchy, provenance pointers,
    confidence scores, and verification status on every edge write.
    """

    _SAFETY_CRITICAL_KEYWORDS = {"pressure", "temperature", "inspection", "isolation", "material"}

    # Relationship types that record PROVENANCE or STRUCTURE, never a claim about the asset.
    # Two of these on one asset is the normal, expected state — an archive holding several
    # documents about a pump is what an archive IS, and a document mentioning two people is not
    # a disagreement about who they are. `detect_conflict` must never fire on them.
    #
    # This mattered: 93 of 94 live conflicts were `DOCUMENTED_BY`, so the entire governance queue
    # was co-documentation reported as contradiction, and the one real engineering conflict
    # (HE-301, 18.5 bar against 16.2 bar) was pushed off the first page by the noise.
    #
    # WHY THIS IS A TYPE LIST AND NOT A VALUE COMPARISON. The honest check would be "do these two
    # edges assert different values", but a KNOWLEDGE_EDGE has no value property — the six
    # mandatory props are validity, authority, document, confidence and verification status.
    # There is nothing to compare, which is also why `source_a` carries no `value` for these rows.
    # Adding one is a schema change plus a backfill of every existing edge, i.e. a cloud write,
    # so the correct move at this scale is to stop asking the question of edges that cannot
    # answer it. Revisit if edges ever carry their asserted value.
    NON_ASSERTING_RELATIONSHIPS = frozenset({
        "DOCUMENTED_BY",             # Asset → Document: provenance, not a claim
        "MENTIONS_PERSON",           # Document → Person: extraction provenance
        "MENTIONS_ORGANISATION",     # Document → Organisation: extraction provenance
        "CONTAINS_TOPOLOGY_ELEMENT", # Document → element: structural
    })

    @classmethod
    def is_asserting_relationship(cls, relationship_type: str | None) -> bool:
        """True when this edge type makes a claim that another source could contradict.

        Shared with `routers/governance.py`, which applies the same rule when reading the
        conflicts already stored in Supabase — those rows predate this guard and cannot be
        deleted (cloud data), so they are filtered on the way out instead.
        """
        return (relationship_type or "").upper() not in cls.NON_ASSERTING_RELATIONSHIPS

    def __init__(self, driver: AsyncDriver, database: str | None = None):
        self.driver = driver
        # Default to the configured database, not a hardcoded "neo4j" — Aura names its DB after the
        # instance ID (e.g. "2016aa75"), so callers that omit `database` must still hit the right one.
        if database is None:
            from api.config import settings
            database = settings.NEO4J_DATABASE
        self.database = database

    async def health_check(self) -> bool:
        try:
            async with self.driver.session(database=self.database) as session:
                result = await session.run("RETURN 1 AS ok")
                await result.single()
            return True
        except Exception as e:
            log.error("neo4j.health_check_failed", error=str(e))
            return False

    # -------------------------------------------------------------------------
    # Asset nodes (Layer 1)
    # -------------------------------------------------------------------------

    async def create_asset_node(self, asset_data: dict[str, Any]) -> str:
        """
        Creates or merges a canonical asset node. If parent_asset_id is provided,
        creates a PARENT_OF relationship from parent to this asset.
        """
        node_cypher = """
        MERGE (a:Asset {asset_id: $asset_id})
        ON CREATE SET
            a.tag_number = $tag_number,
            a.name = $name,
            a.equipment_class = $equipment_class,
            a.criticality = $criticality,
            a.site_id = $site_id,
            a.facility_id = $facility_id,
            a.eam_source = $eam_source,
            a.identity_confirmed = $identity_confirmed,
            a.created_at = $created_at
        RETURN a.asset_id AS asset_id
        """
        parent_cypher = """
        MATCH (parent:Asset {asset_id: $parent_asset_id})
        MATCH (child:Asset {asset_id: $asset_id})
        MERGE (parent)-[:PARENT_OF]->(child)
        """
        async with self.driver.session(database=self.database) as session:
            params = {k: v for k, v in asset_data.items() if k != "parent_asset_id"}
            params["created_at"] = datetime.now(UTC).isoformat()
            result = await session.run(node_cypher, **params)
            record = await result.single()
            asset_id = record["asset_id"]

            if asset_data.get("parent_asset_id"):
                await session.run(
                    parent_cypher,
                    parent_asset_id=asset_data["parent_asset_id"],
                    asset_id=asset_id,
                )
        return asset_id

    async def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        cypher = "MATCH (a:Asset {asset_id: $asset_id}) RETURN a"
        async with self.driver.session(database=self.database) as session:
            result = await session.run(cypher, asset_id=asset_id)
            record = await result.single()
            return dict(record["a"]) if record else None

    async def existing_asset_ids(self, asset_ids: list[str]) -> set[str]:
        """Which of these asset_ids already exist. One round-trip, not one per id.

        UNWIND rather than a loop of `get_asset` calls: a golden-record import checks thousands
        of ids at once, and the per-id form turns an existence check into the slowest part of
        the import. Uses the `asset_id_unique` index, so each lookup is a seek.
        """
        if not asset_ids:
            return set()
        cypher = """
        UNWIND $asset_ids AS aid
        MATCH (a:Asset {asset_id: aid})
        RETURN a.asset_id AS asset_id
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(cypher, asset_ids=asset_ids)
            return {record["asset_id"] async for record in result}

    async def list_assets(
        self,
        site_id: str | None = None,
        equipment_class: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Returns paginated asset list with total count. Authority pre-filter before traversal."""
        where_clauses = []
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if site_id:
            where_clauses.append("a.site_id = $site_id")
            params["site_id"] = site_id
        if equipment_class:
            where_clauses.append("a.equipment_class = $equipment_class")
            params["equipment_class"] = equipment_class

        where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        list_cypher = f"""
        MATCH (a:Asset) {where}
        RETURN a
        ORDER BY a.created_at DESC
        SKIP $skip LIMIT $limit
        """
        count_cypher = f"MATCH (a:Asset) {where} RETURN count(a) AS total"

        async with self.driver.session(database=self.database) as session:
            count_result = await session.run(count_cypher, **{k: v for k, v in params.items() if k not in ("skip", "limit")})
            count_record = await count_result.single()
            total = count_record["total"] if count_record else 0

            list_result = await session.run(list_cypher, **params)
            assets = [dict(record["a"]) async for record in list_result]

        return {"assets": assets, "total": total}

    async def get_asset_hierarchy(self, asset_id: str) -> dict[str, Any] | None:
        """
        Returns the asset's position in the hierarchy:
        ancestors (walk up the PARENT_OF chain, bounded by `MAX_TRAVERSAL_DEPTH`) and direct
        children.
        """
        asset_cypher = "MATCH (a:Asset {asset_id: $asset_id}) RETURN a"
        # Depth interpolated from the module policy, not written inline. Cypher cannot parameterise
        # a variable-length bound (`*1..$n` is a syntax error), so it is an f-string over an int
        # constant — never over user input.
        ancestors_cypher = f"""
        MATCH (a:Asset {{asset_id: $asset_id}})<-[:PARENT_OF*1..{MAX_TRAVERSAL_DEPTH}]-(ancestor:Asset)
        RETURN DISTINCT ancestor
        ORDER BY ancestor.created_at ASC
        """
        children_cypher = """
        MATCH (a:Asset {asset_id: $asset_id})-[:PARENT_OF]->(child:Asset)
        RETURN child
        """
        async with self.driver.session(database=self.database) as session:
            asset_result = await session.run(asset_cypher, asset_id=asset_id)
            asset_record = await asset_result.single()
            if not asset_record:
                return None

            asset = dict(asset_record["a"])

            anc_result = await session.run(ancestors_cypher, asset_id=asset_id)
            ancestors = [dict(record["ancestor"]) async for record in anc_result]

            ch_result = await session.run(children_cypher, asset_id=asset_id)
            children = [dict(record["child"]) async for record in ch_result]

        return {"asset": asset, "ancestors": ancestors, "children": children}

    # -------------------------------------------------------------------------
    # Knowledge edges (Layer 4 — all five properties enforced)
    # -------------------------------------------------------------------------

    # Maps Neo4j node labels to their primary key property name
    _LABEL_ID_FIELD = {
        "Asset": "asset_id",
        "Document": "document_id",
        "Event": "event_id",
        "Concept": "concept_id",
        "Person": "person_id",
        "Organisation": "org_id",
    }

    async def merge_document_node(self, document_id: str, props: dict[str, Any] | None = None) -> None:
        """MERGE a Document node into Neo4j (idempotent). Called before creating edges to it."""
        cypher = """
        MERGE (d:Document {document_id: $document_id})
        ON CREATE SET d += $props, d.created_at = $created_at
        """
        async with self.driver.session(database=self.database) as session:
            await session.run(
                cypher,
                document_id=document_id,
                props=props or {},
                created_at=datetime.now(UTC).isoformat(),
            )

    async def merge_concept_node(self, concept_id: str, props: dict[str, Any] | None = None) -> None:
        """MERGE a Concept node into Neo4j (idempotent). Used for topology elements, regulations, etc."""
        cypher = """
        MERGE (c:Concept {concept_id: $concept_id})
        ON CREATE SET c += $props, c.created_at = $created_at
        """
        async with self.driver.session(database=self.database) as session:
            await session.run(
                cypher,
                concept_id=concept_id,
                props=props or {},
                created_at=datetime.now(UTC).isoformat(),
            )

    async def merge_event_node(
        self,
        event_id: str,
        event_type: str,
        occurred_at: str,
        asset_id: str | None = None,
        props: dict[str, Any] | None = None,
    ) -> None:
        """MERGE an Event node and link it to its asset (Layer 4).

        `Event` is one of the six designed node types and the only one with an index already
        declared for it (`event_type_idx`, `event_occurred_idx` in `init_schema.cypher`) that
        nothing ever wrote to. Operational events lived only in Supabase, so a graph traversal
        could not reach them: `get_last_inspection_date` originally matched `(e:Event)` and was
        therefore permanently `null`, and was rewritten to read an edge instead.

        The `OCCURRED_ON` edge is a plain relationship, not a `KNOWLEDGE_EDGE` — an event is a
        fact about the world with its own timestamp, not a temporal knowledge assertion that
        could be superseded or carry an authority level. Overloading `KNOWLEDGE_EDGE` here would
        put rows into every authority-filtered query that are not knowledge claims.

        Best-effort by design: Supabase is the system of record for events, so a graph write
        failure must never fail the event ingest.
        """
        cypher = """
        MERGE (e:Event {event_id: $event_id})
        ON CREATE SET e.event_type = $event_type,
                      e.occurred_at = $occurred_at,
                      e.asset_id = $asset_id,
                      e += $props,
                      e.created_at = $created_at
        WITH e
        OPTIONAL MATCH (a:Asset {asset_id: $asset_id})
        // Conditional MERGE: an event may reference no asset (plant-state changes) or an asset
        // not yet in the MDM backbone. FOREACH-over-a-CASE is the idiom that skips the write
        // without a subquery — `CALL { }` without a variable scope clause is deprecated, and a
        // plain MATCH would drop the Event row entirely when the asset is absent.
        FOREACH (_ IN CASE WHEN a IS NULL THEN [] ELSE [1] END |
            MERGE (a)-[:OCCURRED_ON]->(e)
        )
        RETURN e.event_id AS event_id
        """
        try:
            async with self.driver.session(database=self.database) as session:
                await session.run(
                    cypher,
                    event_id=str(event_id),
                    event_type=event_type,
                    occurred_at=occurred_at,
                    asset_id=asset_id,
                    props=props or {},
                    created_at=datetime.now(UTC).isoformat(),
                )
        except Exception as exc:
            log.warning(
                "graph.event_node_failed",
                event_id=str(event_id), event_type=event_type, error=str(exc),
            )

    @staticmethod
    def entity_node_id(entity_type: str, text: str) -> str:
        """Deterministic node id for an extracted PERSON / ORGANIZATION.

        Same person named in two documents must MERGE onto one node, so the id is derived from
        the normalised surface form rather than generated — a uuid would create a new node per
        mention and the graph would hold ten "Rohit Menon"s with one edge each.

        Deliberately naive: case-folded, whitespace-collapsed. Real entity resolution (nicknames,
        initials, transliteration) is Layer 1's job for assets and is not attempted here; two
        spellings of a name stay two nodes, which is visible and fixable, rather than being
        silently merged onto the wrong person.
        """
        slug = "-".join(text.split()).upper()
        prefix = "PERSON" if entity_type.upper() == "PERSON" else "ORG"
        return f"{prefix}-{slug}"

    async def merge_person_node(self, person_id: str, props: dict[str, Any] | None = None) -> None:
        """MERGE a Person node (idempotent). Layer 4 designates Person a first-class node type."""
        cypher = """
        MERGE (p:Person {person_id: $person_id})
        ON CREATE SET p += $props, p.created_at = $created_at
        """
        async with self.driver.session(database=self.database) as session:
            await session.run(
                cypher,
                person_id=person_id,
                props=props or {},
                created_at=datetime.now(UTC).isoformat(),
            )

    async def merge_organisation_node(self, org_id: str, props: dict[str, Any] | None = None) -> None:
        """MERGE an Organisation node (idempotent).

        Label is `Organisation` — the spelling `db/neo4j/init_schema.cypher` declares the
        uniqueness constraint for and seeds `KAIROS_PLATFORM` under. `Organization` would create
        a second, unconstrained label that looks identical in query output.
        """
        cypher = """
        MERGE (o:Organisation {org_id: $org_id})
        ON CREATE SET o += $props, o.created_at = $created_at
        """
        async with self.driver.session(database=self.database) as session:
            await session.run(
                cypher,
                org_id=org_id,
                props=props or {},
                created_at=datetime.now(UTC).isoformat(),
            )

    async def detect_conflict(
        self,
        source_id: str,
        source_label: str,
        relationship_type: str,
        new_document_id: str,
        new_authority_level: int,
    ) -> dict[str, Any] | None:
        """
        Checks for an active edge on the same (source, relationship_type) from a DIFFERENT document.
        Returns conflict metadata dict for Supabase insert, or None if no conflict.

        Only *asserting* relationship types are considered — see `NON_ASSERTING_RELATIONSHIPS`.
        A second document documenting the same asset is not a contradiction, and treating it as
        one made 93 of 94 conflicts noise.
        """
        if source_label not in self._LABEL_ID_FIELD:
            return None
        # Provenance and structural edges cannot contradict one another. Checked before the query
        # so the common path also stops paying for a Neo4j round trip per ingested document.
        if not self.is_asserting_relationship(relationship_type):
            return None
        src_field = self._LABEL_ID_FIELD[source_label]
        # Safe: src_field and source_label come from validated whitelist
        cypher = f"""
        MATCH (src:{source_label} {{{src_field}: $source_id}})-[r:KNOWLEDGE_EDGE]->(existing)
        WHERE r.relationship_type = $relationship_type
          AND (r.valid_to IS NULL OR datetime(r.valid_to) > datetime())
          AND r.document_id <> $new_document_id
          AND r.verification_status <> 'superseded'
        RETURN r.edge_id AS edge_id, r.document_id AS document_id,
               r.authority_level AS authority_level, r.confidence AS confidence
        LIMIT 1
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                cypher,
                source_id=source_id,
                relationship_type=relationship_type,
                new_document_id=new_document_id,
            )
            record = await result.single()
        if not record:
            return None

        param_lower = relationship_type.lower()
        is_safety_param = any(kw in param_lower for kw in self._SAFETY_CRITICAL_KEYWORDS)
        track = "engineering" if (new_authority_level <= 3 and is_safety_param) else "administrative"
        sla_hours = 24 if track == "engineering" else 5 * 24
        severity = "critical" if new_authority_level == 1 else ("major" if track == "engineering" else "minor")

        return {
            "parameter": relationship_type,
            "track": track,
            "severity": severity,
            "source_a": {"edge_id": record["edge_id"], "document_id": record["document_id"],
                         "authority_level": record["authority_level"], "confidence": record["confidence"]},
            "source_b": {"document_id": new_document_id, "authority_level": new_authority_level},
            "authority_a": record["authority_level"],
            "authority_b": new_authority_level,
            "sla_hours": sla_hours,
        }

    # Sentinel: stored as valid_to when the edge has no expiry yet.
    # Neo4j drops null properties, so we use far-future to guarantee the key exists.
    _OPEN_VALID_TO = datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC)

    async def create_knowledge_edge(
        self,
        source_id: str,
        source_label: str,
        target_id: str,
        target_label: str,
        relationship_type: str,
        # Six mandatory edge properties:
        valid_from: datetime,
        authority_level: int,
        document_id: str,
        confidence: float,
        verification_status: str = "unverified",
        valid_to: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Creates a temporal knowledge edge with all six mandatory properties.
        Labels must be from the known node label set (validated against whitelist).
        Returns {"edge_id": str, "conflict": dict|None} — conflict is non-None when
        an existing active edge for the same (source, relationship_type) was found.
        """
        if source_label not in self._LABEL_ID_FIELD or target_label not in self._LABEL_ID_FIELD:
            raise ValueError(f"Unknown label: {source_label!r} or {target_label!r}")
        if not (1 <= authority_level <= 5):
            raise ValueError(f"authority_level must be 1-5, got {authority_level}")
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(f"confidence must be 0.0-1.0, got {confidence}")

        src_field = self._LABEL_ID_FIELD[source_label]
        tgt_field = self._LABEL_ID_FIELD[target_label]
        edge_id = f"{source_id}_{relationship_type}_{target_id}_{valid_from.isoformat()}"

        # Detect conflict before writing (labels come from validated whitelist — f-string safe)
        conflict = await self.detect_conflict(
            source_id=source_id,
            source_label=source_label,
            relationship_type=relationship_type,
            new_document_id=document_id,
            new_authority_level=authority_level,
        )

        cypher = f"""
        MATCH (src:{source_label} {{{src_field}: $source_id}})
        MATCH (tgt:{target_label} {{{tgt_field}: $target_id}})
        CREATE (src)-[r:KNOWLEDGE_EDGE {{
            edge_id: $edge_id,
            relationship_type: $relationship_type,
            valid_from: $valid_from,
            valid_to: $valid_to,
            authority_level: $authority_level,
            document_id: $document_id,
            confidence: $confidence,
            verification_status: $verification_status
        }}]->(tgt)
        RETURN r.edge_id AS edge_id
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                cypher,
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
                edge_id=edge_id,
                valid_from=valid_from.isoformat(),
                valid_to=(valid_to or self._OPEN_VALID_TO).isoformat(),
                authority_level=authority_level,
                document_id=document_id,
                confidence=confidence,
                verification_status=verification_status,
            )
            record = await result.single()

        return {"edge_id": record["edge_id"] if record else edge_id, "conflict": conflict}

    async def close_validity_window(self, edge_id: str, valid_to: datetime) -> None:
        """Closes the validity window on an edge (supersession, never deletion)."""
        cypher = """
        MATCH ()-[r:KNOWLEDGE_EDGE {edge_id: $edge_id}]->()
        SET r.valid_to = $valid_to, r.verification_status = 'superseded'
        """
        async with self.driver.session(database=self.database) as session:
            await session.run(cypher, edge_id=edge_id, valid_to=valid_to.isoformat())

    async def close_validity_windows_for_document(self, document_id: str, valid_to: datetime) -> int:
        """
        Closes all active edges that reference a specific document (document supersession).
        Returns the count of edges closed. Never deletes — only sets valid_to + status.
        """
        cypher = """
        MATCH ()-[r:KNOWLEDGE_EDGE {document_id: $document_id}]-()
        WHERE (r.valid_to IS NULL OR datetime(r.valid_to) > datetime())
        SET r.valid_to = $valid_to, r.verification_status = 'superseded'
        RETURN count(r) AS closed
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(cypher, document_id=document_id, valid_to=valid_to.isoformat())
            record = await result.single()
            return record["closed"] if record else 0

    async def get_verified_topology_for_asset(
        self,
        asset_tag: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Engineer-verified P&ID elements on the drawing that contains `asset_tag`.

        **Only `verification_status = 'verified'` elements are ever returned.** An unverified
        element is a vision model's candidate reading of a drawing, and the architecture is
        explicit that topology is not canonical until an engineer has confirmed it
        element-by-element. Returning an unverified element here would launder an extraction into
        an isolation claim — the single worst failure this system can have.

        The join is by element **label**, not by an `Asset`→`Document` edge: the extraction writes
        `(:Document)-[:KNOWLEDGE_EDGE {relationship_type:'CONTAINS_TOPOLOGY_ELEMENT'}]->(:Concept)`
        and the asset appears as a `Concept.label` (V-247 is an `equipment_nodes` element), so the
        drawing is located *through* the asset rather than pointed at by it. `brief_engine` used to
        query `(:Asset)-[{relationship_type:'pid_topology'}]->()`, a relationship type nothing ever
        writes and a direction that does not exist — so it silently returned `[]` for every asset,
        which is why PTW briefs carried no isolation devices. Callers must share this one query.
        """
        cypher = """
        MATCH (d:Document)-[:KNOWLEDGE_EDGE {relationship_type: 'CONTAINS_TOPOLOGY_ELEMENT'}]
              ->(anchor:Concept)
        WHERE toUpper(anchor.label) = toUpper($asset_tag)
        WITH DISTINCT d
        MATCH (d)-[r:KNOWLEDGE_EDGE {relationship_type: 'CONTAINS_TOPOLOGY_ELEMENT'}]->(c:Concept)
        WHERE r.verification_status = 'verified'
          AND (r.valid_to IS NULL OR datetime(r.valid_to) > datetime())
        RETURN c.concept_id   AS element_id,
               c.label        AS label,
               c.element_type AS element_type,
               d.document_id  AS document_id,
               r.authority_level    AS authority_level,
               r.confidence         AS confidence,
               r.verified_by        AS verified_by,
               r.verification_status AS verification_status
        ORDER BY c.element_type, c.label
        LIMIT $limit
        """
        try:
            async with self.driver.session(database=self.database) as session:
                result = await session.run(cypher, asset_tag=asset_tag, limit=limit)
                return [dict(r) async for r in result]
        except Exception as exc:
            log.warning("graph.verified_topology_failed", asset_tag=asset_tag, error=str(exc))
            return []

    async def set_topology_element_verification(
        self,
        document_id: str,
        element_id: str,
        verification_status: str,
        verified_by: str,
    ) -> int:
        """
        Flips a P&ID topology element's edge to its post-review state (Layer 3 → Layer 7 gate).

        The ingestion pipeline already writes a `CONTAINS_TOPOLOGY_ELEMENT` edge per element with
        `verification_status='unverified'`, so engineer verification *promotes an existing edge*
        rather than creating a new one — element-by-element, which is what the architecture
        requires before topology may be treated as canonical.

        Returns the number of edges updated (0 if the element has no edge, e.g. the edge write
        failed during extraction).
        """
        cypher = """
        MATCH (d:Document {document_id: $document_id})
              -[r:KNOWLEDGE_EDGE {relationship_type: 'CONTAINS_TOPOLOGY_ELEMENT'}]->
              (c:Concept {concept_id: $element_id})
        SET r.verification_status = $verification_status,
            r.verified_by = $verified_by,
            r.verified_at = datetime()
        RETURN count(r) AS updated
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                cypher,
                document_id=document_id,
                element_id=element_id,
                verification_status=verification_status,
                verified_by=verified_by,
            )
            record = await result.single()
            return record["updated"] if record else 0

    # -------------------------------------------------------------------------
    # Time-travel queries (Layer 4)
    # -------------------------------------------------------------------------

    async def get_asset_knowledge_at(
        self,
        asset_id: str,
        as_of: datetime | None = None,
        authority_min: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Returns all temporal graph edges for an asset, optionally scoped to a
        historical point-in-time.

        There is no composite index on (asset_id, valid_from, valid_to) — that
        composite cannot exist, because asset_id is a node property and the
        validity window is a relationship property. PROFILE (2026-08-22) shows the
        real plan: anchor on the Asset, Expand(All), then Filter the edges. The
        KNOWLEDGE_EDGE property indexes are not consulted for edges reached by
        expansion, so they do not serve this query. The anchor is what matters —
        it needs `asset_id_unique` present, or this plans as a NodeByLabelScan
        over every Asset. See db/neo4j/init_schema.cypher.
        """
        as_of_str = as_of.isoformat() if as_of else datetime.now(UTC).isoformat()
        cypher = """
        MATCH (a:Asset {asset_id: $asset_id})-[r:KNOWLEDGE_EDGE]->(target)
        WHERE r.valid_from <= $as_of
          AND (r.valid_to IS NULL OR r.valid_to > $as_of)
          AND r.authority_level <= $authority_min
        RETURN r, target
        ORDER BY r.authority_level ASC, r.valid_from DESC
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                cypher,
                asset_id=asset_id,
                as_of=as_of_str,
                authority_min=authority_min,
            )
            # Dedupe by edge_id property: the graph can hold multiple physical KNOWLEDGE_EDGE
            # relationships that share one logical edge_id (Cypher DISTINCT can't collapse them
            # — they're separate graph elements). Keep the first, drop repeats.
            seen: set[str] = set()
            facts: list[dict[str, Any]] = []
            async for record in result:
                edge = dict(record["r"])
                edge_id = edge.get("edge_id")
                if edge_id in seen:
                    continue
                seen.add(edge_id)
                facts.append({"edge": edge, "target": dict(record["target"])})
            return facts

    # -------------------------------------------------------------------------
    # Blast-radius analysis (Layer 7)
    # -------------------------------------------------------------------------

    async def get_event_timeline(
        self,
        asset_id: str,
        window_start: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Returns Event nodes linked to an asset (by property or relationship)
        with occurred_at >= window_start, ordered chronologically.
        """
        cypher = """
        MATCH (e:Event)
        WHERE (e.asset_id = $asset_id
               OR EXISTS { MATCH (a:Asset {asset_id: $asset_id})-[]->(e) })
          AND e.occurred_at >= $window_start
        RETURN DISTINCT
            e.event_id   AS event_id,
            e.event_type AS event_type,
            e.occurred_at AS occurred_at,
            e.description AS description,
            e.document_id AS document_id,
            e.source      AS source
        ORDER BY e.occurred_at ASC
        LIMIT $limit
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(cypher, asset_id=asset_id, window_start=window_start, limit=limit)
            return [
                {
                    "event_id": r["event_id"],
                    "event_type": r["event_type"],
                    "occurred_at": r["occurred_at"],
                    "description": r["description"] or "",
                    "document_id": r["document_id"],
                    "source": r["source"] or "neo4j",
                }
                async for r in result
            ]

    async def get_blast_radius(self, document_id: str) -> dict[str, Any]:
        """
        Traverses the graph to find all facts and downstream relationships
        that derive from the specified document (provenance_pointer = document_id).
        """
        # Return both endpoints: the affected entity is the edge SOURCE (e.g. the asset
        # whose knowledge derives from this document); the target is usually the document
        # node itself. Dedupe by edge_id — re-runs can leave duplicate relationships.
        cypher = """
        MATCH (source)-[r:KNOWLEDGE_EDGE {document_id: $document_id}]->(target)
        RETURN r, source, target
        LIMIT 500
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(cypher, document_id=document_id)
            seen: set = set()
            affected = []
            async for record in result:
                edge = dict(record["r"])
                edge_id = edge.get("edge_id")
                if edge_id and edge_id in seen:
                    continue
                if edge_id:
                    seen.add(edge_id)
                affected.append({
                    "edge": edge,
                    "source": dict(record["source"]),
                    "target": dict(record["target"]),
                })
            return {"document_id": document_id, "affected_count": len(affected), "affected": affected}

    async def get_last_inspection_date(self, asset_id: str) -> str | None:
        """
        Most recent inspection date for an asset, from the `INSPECTION_RECORD` edge.

        This used to `MATCH (e:Event)`. **No `Event` node is ever written** — events live in
        Supabase `operational_events`, and only Asset / Document / Concept are materialised in
        the graph (the L4 divergence in `implementation/status.md`). So the query matched
        nothing and the asset-detail `last_inspection_date` was **always null**: it degraded
        cleanly, which is exactly why it went unnoticed.

        The real record is the `INSPECTION_RECORD` relationship written by
        `POST /events/inspection-complete` (`routers/events.py`), whose `valid_from` is the
        inspection time. Reading the edge that is actually written makes the field work without
        materialising Event nodes.

        Superseded edges are excluded — a retracted inspection must not read as the latest one.
        """
        cypher = """
        MATCH (a:Asset {asset_id: $asset_id})-[r:INSPECTION_RECORD]->(:Document)
        WHERE r.verification_status <> 'superseded'
        RETURN r.valid_from AS inspection_date
        ORDER BY r.valid_from DESC LIMIT 1
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(cypher, asset_id=asset_id)
            record = await result.single()
            if record and record["inspection_date"]:
                val = record["inspection_date"]
                return val.isoformat() if hasattr(val, "isoformat") else str(val)
            return None
