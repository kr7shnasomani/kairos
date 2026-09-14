// Kairos Neo4j Schema — Temporal Reality Graph
// Run: python backend/scripts/init_neo4j.py
// Or directly via Neo4j Browser

// =============================================================================
// CONSTRAINTS — Uniqueness on primary identifiers
// =============================================================================

CREATE CONSTRAINT asset_id_unique IF NOT EXISTS
FOR (a:Asset) REQUIRE a.asset_id IS UNIQUE;

CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.document_id IS UNIQUE;

CREATE CONSTRAINT event_id_unique IF NOT EXISTS
FOR (e:Event) REQUIRE e.event_id IS UNIQUE;

CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.person_id IS UNIQUE;

CREATE CONSTRAINT concept_id_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE c.concept_id IS UNIQUE;

CREATE CONSTRAINT org_id_unique IF NOT EXISTS
FOR (o:Organisation) REQUIRE o.org_id IS UNIQUE;

// =============================================================================
// INDICES — Performance for temporal queries (hot paths)
//
// NOT a composite index on (asset_id, valid_from, valid_to), despite what
// ARCHITECTURE.md §7 asks for. Two reasons, both structural:
//
//   1. `asset_id` is a property of the :Asset NODE; the validity window lives on
//      the KNOWLEDGE_EDGE RELATIONSHIP. There is no single entity carrying all
//      three properties, so that composite cannot be declared as written.
//   2. The hot-path queries anchor on (a:Asset {asset_id: $id}) and EXPAND, then
//      filter r.valid_from/r.valid_to on the edges they reach. A relationship
//      index serves relationship SCANS — it is not consulted for edges already
//      reached by expansion — so adding one would likely be a no-op here.
//
// Whether the temporal filter can be pushed before expansion is a query-planner
// question that needs PROFILE against a populated graph, not a DDL change. The
// single-property edge indexes below are correct and useful regardless of how
// that lands. See TODO.md §3 (graph query policy).
// =============================================================================

// Asset lookup
CREATE INDEX asset_tag_idx IF NOT EXISTS FOR (a:Asset) ON (a.tag_number);
CREATE INDEX asset_site_idx IF NOT EXISTS FOR (a:Asset) ON (a.site_id);
CREATE INDEX asset_class_idx IF NOT EXISTS FOR (a:Asset) ON (a.equipment_class);
CREATE INDEX asset_criticality_idx IF NOT EXISTS FOR (a:Asset) ON (a.criticality);

// Document lookup
CREATE INDEX document_type_idx IF NOT EXISTS FOR (d:Document) ON (d.document_type);
CREATE INDEX document_status_idx IF NOT EXISTS FOR (d:Document) ON (d.status);
CREATE INDEX document_authority_idx IF NOT EXISTS FOR (d:Document) ON (d.authority_level);

// Event lookup
CREATE INDEX event_type_idx IF NOT EXISTS FOR (e:Event) ON (e.event_type);
CREATE INDEX event_occurred_idx IF NOT EXISTS FOR (e:Event) ON (e.occurred_at);

// =============================================================================
// EDGE PROPERTY INDICES — Critical for temporal validity window queries
// =============================================================================

CREATE INDEX edge_valid_from_idx IF NOT EXISTS
FOR ()-[r:KNOWLEDGE_EDGE]-() ON (r.valid_from);

// Both ends of the window need covering: every temporal query filters on
// valid_to as well (open edges carry the 9999-12-31 sentinel, never NULL), and
// superseded-edge lookups filter on valid_to alone.
CREATE INDEX edge_valid_to_idx IF NOT EXISTS
FOR ()-[r:KNOWLEDGE_EDGE]-() ON (r.valid_to);

CREATE INDEX edge_authority_idx IF NOT EXISTS
FOR ()-[r:KNOWLEDGE_EDGE]-() ON (r.authority_level);

CREATE INDEX edge_verification_idx IF NOT EXISTS
FOR ()-[r:KNOWLEDGE_EDGE]-() ON (r.verification_status);

CREATE INDEX edge_document_idx IF NOT EXISTS
FOR ()-[r:KNOWLEDGE_EDGE]-() ON (r.document_id);

// =============================================================================
// SEED: Root organisation node
// =============================================================================

MERGE (o:Organisation {org_id: 'KAIROS_PLATFORM'})
SET o.name = 'Kairos Platform',
    o.type = 'platform',
    o.created_at = datetime();
