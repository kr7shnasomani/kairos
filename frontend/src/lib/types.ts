// API types — derived from docs/API.md. The contract for both live and fixture data.

// Mirrors the roles in infra/policies/kairos.rego. `compliance` is a read-only auditor
// (search + compliance cockpit + audit trail, no writes); it existed in OPA long before the
// frontend knew about it, so a compliance user used to redirect-loop at login.
export type Role = "admin" | "engineer" | "field_worker" | "reliability" | "compliance";

export interface User {
  user_id: string;
  email: string;
  role: Role;
  site_id: string;
}

/** Authority hierarchy (docs/ARCHITECTURE Layer 4). Lower = higher authority. */
export type AuthorityLevel = 1 | 2 | 3 | 4 | 5;

export type BriefPriority = "critical" | "high" | "normal" | "medium" | "low";

export type GovernorStateValue = "normal" | "suppressed";

export interface BriefSource {
  document_id: string;
  document_type: string;
  title: string;
  authority_level: AuthorityLevel;
  relevant_excerpt: string;
  vault_url: string | null;
  is_quarantine: boolean;
}

export interface Brief {
  brief_id: string;
  /** Returned by `GET /briefs/` but previously undeclared here. */
  asset_id?: string | null;
  recipient_user_id: string;
  priority: BriefPriority;
  trigger_event_type: string;
  headline: string;
  body: string;
  action_items: string[];
  warnings: string[];
  sources: BriefSource[];
  requires_countersignature: boolean;
  delivery_frozen: boolean;
  frozen?: boolean;
  freeze_reason?: string | null;
  freeze_deviation_flag_id?: string | null;
  delivered_at: string;
  acknowledged_at?: string | null;
  /** Set at ack time. For PTW briefs this alone is NOT completion — a countersignature is
   *  still required, and `acknowledged_at` stays null until it arrives (architecture Flow B). */
  acknowledged_by?: string | null;
  countersigned_by?: string | null;
  countersigned_at?: string | null;
  acknowledged_by_name?: string | null;
  countersigned_by_name?: string | null;
}

export interface GovernorState {
  push_count_last_hour: number;
  ceiling: number;
  state: GovernorStateValue;
}

export interface BriefsResponse {
  briefs: Brief[];
  total_pending: number;
  suppressed_count: number;
  /** Briefs the EEMUA governor or plant state is withholding. Disclosed, never delivered —
   *  they are deliberately not in `briefs`, because the backend records a push for everything
   *  it delivers and that would spend governor budget on briefs the governor is holding back. */
  suppressed_held?: Brief[];
  governor_state: GovernorState;
  next_delivery_allowed_at: string | null;
}

// --- Search / synthesize (Layer 11) ---
export interface SynthesizeSource {
  document_id: string;
  authority_level: AuthorityLevel;
}

export interface SynthesizeResponse {
  answer: string | null;
  sources: SynthesizeSource[];
  confidence: number;
  refused: boolean;
  refusal_reason?: string;
  safety_critical: boolean;
  sources_used?: number[];
  model?: string;
}

// --- RCA pack ---
export interface RcaTimelineEvent {
  event_type: string;
  occurred_at: string;
  description: string;
  source: string;
}

export interface RcaHypothesis {
  hypothesis: string;
  evidence_weight: number;
  sources: string[];
  refused?: boolean;
}

export interface RcaSupportingDoc {
  document_id: string;
  title: string;
  authority_level: AuthorityLevel;
  confidence: number;
}

export interface RcaPack {
  asset_id: string;
  incident_date: string;
  failure_code: string;
  timeline: RcaTimelineEvent[];
  hypotheses: RcaHypothesis[];
  supporting_documents: RcaSupportingDoc[];
  /** `null` = not reported by the model, not zero. `result-header.tsx` already had a
   *  `Number.isFinite` guard rendering "Confidence —", but `getRcaPack` coerced null to 0,
   *  so that branch was unreachable and the meter always drew a real-looking score. */
  confidence: number | null;
  refused: boolean;
  synthesis_available: boolean;
}

/** Generic list envelope used by /assets, /governance/*, /compliance/gaps (MEMORY task 25). */
export interface ListEnvelope<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// --- Compliance (GET /compliance/gaps, /dashboard) ---
// severity is derived server-side from authority_level: 1→critical, 2→major, else minor.
export type GapSeverity = "critical" | "major" | "minor";

export interface ComplianceGap {
  concept_id?: string;
  framework: string;
  clause_id: string;
  requirement_text: string;
  applies_to?: string | null;
  authority_level: AuthorityLevel;
  asset_id: string;
  tag_number?: string | null;
  equipment_class?: string | null;
  site_id?: string | null;
  severity: GapSeverity;
  suggested_remediation?: string | null;
  /** `gap` = no document of the required type exists. `unverified_evidence` = one exists
   *  but no human has verified the edge. Conflating them is what made every clause read
   *  as non-compliant. */
  status?: "gap" | "unverified_evidence";
  /** Evidence type the clause requires, e.g. ["procedure"]. */
  requires_document_type?: string[] | null;
  evidence_count?: number;
  verified_count?: number;
}

export interface ComplianceGapsResponse {
  items: ComplianceGap[];
  total: number;
  /** Split of `total` by finding kind — a true gap is not the same as unverified evidence. */
  gap_total?: number;
  unverified_total?: number;
  limit: number;
  offset: number;
  framework: string | null;
  last_scan: string;
}

// --- Assets (GET /assets, /assets/{id}) ---
export interface AssetSummary {
  asset_id: string;
  tag_number?: string | null;
  name: string;
  equipment_class: string;
  criticality: string; // safety_critical | critical | non_critical
  site_id?: string | null;
  parent_asset_id?: string | null;
  /**
   * Issue counts, now returned by `GET /assets/` as well as `GET /assets/{id}` — the list
   * previously omitted them, which blocked two columns the design review asked for.
   * Always numeric, never null: an asset with no rows is `0`. A backend lookup failure also
   * yields `0` (logged server-side), so these are "best known", not guaranteed-live.
   */
  open_work_orders_count: number;
  compliance_gap_count: number;
}

export interface AssetsResponse {
  items: AssetSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface AssetDetail extends AssetSummary {
  // open_work_orders_count / compliance_gap_count are inherited from AssetSummary — the list
  // endpoint returns them too now, so they are no longer detail-only.
  last_inspection_date: string | null;
}

// --- Governance: conflicts (GET /governance/conflicts) ---
export type ConflictTrack = "administrative" | "engineering";
export type ConflictStatus = "open" | "pending_moc" | "resolved";

/** A conflict source is a JSON blob from Supabase, and the two producers write different keys.
 *  `services/graph.py detect_conflict` writes `document_id` / `authority_level` / `edge_id` /
 *  `confidence` and **no `value`** — it never compares what the edges assert, so there is no
 *  contradicting value to record. The seeded engineering conflict (HE-301 pressure limit) does
 *  carry `value` and a human-readable `source`. Every field is therefore optional, and the UI
 *  has to degrade rather than assume. */
export interface ConflictSource {
  document_id?: string;
  /** The contradicting value, e.g. "18.5 bar". Absent on auto-detected conflicts. */
  value?: string;
  /** Human-readable provenance, e.g. "Meridian OEM Manual (2019)". Absent on auto-detected. */
  source?: string;
  authority_level?: number;
  [key: string]: unknown;
}

export interface Conflict {
  conflict_id: string;
  track: ConflictTrack;
  asset_id: string;
  parameter: string;
  source_a: ConflictSource;
  source_b: ConflictSource;
  authority_a: AuthorityLevel;
  authority_b: AuthorityLevel;
  severity: string;
  status: ConflictStatus;
  sla_due_at: string | null;
  is_overdue: boolean;
  created_at: string;
}

export interface ConflictsResponse {
  items: Conflict[];
  total: number;
  limit: number;
  offset: number;
}

// --- Governance: quarantine (GET /governance/quarantine) ---
export type QuarantineStatus = "pending" | "promoted" | "disputed" | "archived";

export interface QuarantineItem {
  item_id: string;
  asset_id: string | null;
  content: string;
  input_type: string;
  submitted_by: string;
  /** Readable name when `submitted_by` is a signed-in user; absent for services and source-system names. */
  submitted_by_name?: string | null;
  submitted_at: string;
  reviewer_id: string | null;
  reviewer_name?: string | null;
  review_status: QuarantineStatus;
  work_order_id: string | null;
  session_context: Record<string, unknown> | null;
  sla_due_at: string | null;
  is_overdue: boolean;
}

export interface QuarantineResponse {
  items: QuarantineItem[];
  total: number;
  limit: number;
  offset: number;
  note: string;
}

/** Body for POST /governance/quarantine/{id}/promote. */
export interface PromoteQuarantineRequest {
  authority_level: AuthorityLevel;
  relationship_type: string;
  document_type?: string;
  notes?: string;
}

// --- Documents (GET /documents/, /documents/{id}) ---
export type DocumentState = "active" | "superseded";

export interface VaultDocument {
  document_id: string;
  file_name: string;
  /** Layer 3: "ocr" = text read off an image (scans, field forms), "native" = parsed from
   *  digital structure. Derived server-side so the rule has one definition. */
  extraction_path?: "ocr" | "native";
  /** Image-path documents are where handwriting lives. A flag, deliberately not a confidence
   *  penalty — lowering the score would push these under the 0.7 quarantine threshold. */
  handwriting_suspect?: boolean;
  document_type: string; // oem_manual | procedure | inspection_report | ptw | shift_log | regulation | pid_drawing
  authority_level: AuthorityLevel;
  source_system: string;
  vault_url: string | null;
  status: DocumentState;
  ingested_at: string;
  ingested_by: string;
  /** Readable uploader name when the id is a known user; absent for loader/connector ids. */
  ingested_by_name?: string | null;
  file_size_bytes?: number;
  mime_type?: string;
  sha256_hash?: string;
  version_chain?: string | null;
  asset_links?: string[];
  occurred_at?: string | null;
}

export interface DocumentsResponse {
  items: VaultDocument[];
  total: number;
  limit: number;
  offset: number;
  /** Test-sweep artifacts withheld from `items`/`total` — reported rather than silent, same
   *  rule as the knowledge-graph views. Absent on an older backend. */
  excluded_test_documents?: number;
}

// --- Asset knowledge (GET /assets/{id}/knowledge, /aliases) ---
export interface AssetAlias {
  canonical_asset_id?: string;
  alias: string;
  alias_source?: string;
  confirmed?: boolean;
  confidence?: number;
}

/** Raw fact = a temporal KNOWLEDGE_EDGE plus its target node. */
export interface AssetKnowledgeFact {
  edge: Record<string, unknown>;
  target: Record<string, unknown>;
}

export interface AssetKnowledgeResponse {
  asset_id: string;
  as_of: string;
  fact_count: number;
  /** Facts dropped because their source document is a test/sweep artifact. Reported rather than
   *  silent — the denominator has to stay auditable. Absent on an older backend. */
  excluded_test_documents?: number;
  facts: AssetKnowledgeFact[];
}

// --- Compliance dashboard (GET /compliance/dashboard) ---
export interface ComplianceDashboard {
  total_gaps: { critical: number; major: number; minor: number };
  by_framework: Record<string, Record<string, number>>;
  by_asset_class: Record<string, Record<string, number>>;
  last_updated?: string;
}

// --- Governance: SLA report (GET /governance/sla-report) ---
// Shape mirrors the backend exactly — this endpoint is an *escalation* report:
// it exposes only overdue items + escalation counts, not on-time/total tallies.
export interface OverdueConflict {
  conflict_id: string;
  track: ConflictTrack;
  asset_id: string | null;
  sla_deadline: string;
  escalated_at: string | null;
  status: string;
}

export interface OverdueQuarantineItem {
  item_id: string;
  asset_id: string | null;
  input_type: string;
  content?: string;
  sla_due_at: string;
  escalated_at: string | null;
}

export interface SlaReport {
  checked_at: string;
  escalated_this_run: { conflicts: number; quarantine_items: number };
  overdue_conflicts: OverdueConflict[];
  overdue_conflicts_total: number;
  overdue_quarantine_items: OverdueQuarantineItem[];
  overdue_quarantine_total: number;
}

// --- Governance: MoC (GET /governance/moc) ---
// Backend MoC lifecycle: draft → pending_approval → approved | rejected. ("pending" is the
// UI bucket that groups the pre-approval states; see PENDING_STATUSES in the MoC page.)
export type MocStatus = "draft" | "pending_approval" | "pending" | "approved" | "rejected";

export interface MocItem {
  moc_id: string;
  asset_id: string;
  status: MocStatus;
  created_at: string;
  // Live MoC items (auto-drafted EWRs) carry a free-text `description` and `conflict_id`.
  // The structured parameter/source fields only exist on richer/legacy items, so they are
  // optional — the UI falls back to `description` when they are absent.
  description?: string | null;
  conflict_id?: string | null;
  parameter?: string;
  source_a?: ConflictSource;
  source_b?: ConflictSource;
  blast_radius_count?: number;
  draft_content?: string | null;
}

export interface MocResponse {
  items: MocItem[];
  total: number;
  limit: number;
  offset: number;
}

// --- Governance: circuit breaker (GET /governance/circuit-breaker) ---
// Mirrors the backend: one entry per asset_class with override records, `halted`
// a boolean (z_score > 2.0). No halted_since / generated_at are exposed.
export interface CircuitBreakerEntry {
  asset_class: string;
  halted: boolean;
  z_score: number;
  override_count_7d: number;
  reason: string;
}

export interface CircuitBreakerState {
  states: CircuitBreakerEntry[];
  halted_count: number;
}

// --- Governance: model gate ---
export interface EntityTypeScore {
  precision?: number;
  recall?: number;
  f1?: number;
  count?: number;
}

export interface ModelGateResult {
  run_id: string;
  task_id?: string | null;
  precision: number;
  recall: number;
  f1: number;
  passed: boolean;
  corpus_size: number;
  run_at: string;
  /** Model the gate scored. Optional: older audit rows predate the field. */
  model_name?: string;
  /** Per-entity-type breakdown — shows which entity types a model actually fails on. */
  by_entity_type?: Record<string, EntityTypeScore>;
  /**
   * Whether this run may be read as a measurement of the model.
   *
   * `SUSPECT` means some extractions fell back to the regex path, which matches ASSET_TAG only —
   * so the F1 is a **ceiling**, not a score for the model named in the row. Without this the trend
   * plots a fallback-contaminated run identically to a clean one.
   *
   * Optional on purpose: the Celery gate (`workers/model_validation.py`) writes `details: result`
   * without these fields, and every row before 2026-08-15 predates them.
   */
  validity?: "VALID" | "SUSPECT";
  /** Extraction path counts, e.g. `{nim: 15}` or `{nim: 3, regex: 2}`. */
  extraction_paths?: Record<string, number>;
  /** Extractions that did NOT come from the model under test. */
  fallback_extractions?: number;
}

export interface ModelGateHistory {
  history: ModelGateResult[];
}

export interface ModelGateRunResponse {
  task_id: string;
  status: string;
}

// Mirrors GET /governance/validation-corpus/stats — no by_asset_class breakdown.
export interface ValidationCorpusStats {
  total_corpus_size: number;
  by_entity_type: Record<string, number>;
  last_updated_at: string | null;
}

// --- Governance: blast radius ---
export interface BlastRadiusItem {
  item_id: string;
  item_type: string;
  description: string;
  asset_id?: string;
  flagged_for_review: boolean;
}

export interface BlastRadiusReport {
  document_id: string;
  affected_count: number;
  items: BlastRadiusItem[];
  generated_at: string;
}

// --- Annotations (POST /annotations, GET /annotations) ---
export interface Annotation {
  annotation_id: string;
  document_id: string;
  entity_text: string;
  entity_type: string;
  corrected_type?: string | null;
  is_correct: boolean;
  span_start?: number | null;
  span_end?: number | null;
  created_by: string;
  created_at: string;
}

export interface AnnotationStats {
  total: number;
  corrections_this_week: number;
  top_corrected_entity_types: Array<{ type: string; count: number }>;
}

// --- Elicitation (GET /elicitation/{wo}/questions) ---
export interface ElicitationQuestion {
  question_id: string;
  question_text: string;
  context: string;
  options?: string[] | null;
  question_type: "multiple_choice" | "free_text";
}

export interface ElicitationSession {
  session_id: string;
  work_order_id: string;
  asset_id?: string | null;
  questions: ElicitationQuestion[];
  status: "pending" | "in_progress" | "completed";
  created_at: string;
}

// --- Offboarding (GET /elicitation/offboarding) ---
export type OffboardingSessionStatus = "pending" | "questions_ready" | "completed";

// One equipment-family session within a programme (backend: offboarding_session_items row).
export interface OffboardingSessionItem {
  id: string;
  session_number: number;
  equipment_family: string;
  status: OffboardingSessionStatus;
  scheduled_for: string;
  completed_at?: string | null;
}

// GET /elicitation/offboarding (list) → items without session_items but with completion.
// GET /elicitation/offboarding/{id} (detail) → adds session_items, session_interval_days.
export interface OffboardingProgramme {
  id: string;
  personnel_id: string;
  personnel_email: string;
  retirement_date: string;
  total_sessions: number;
  status: string;
  created_at: string;
  sessions_completed?: number;      // list endpoint only
  completion_pct?: number;          // list endpoint only
  session_interval_days?: number;   // detail endpoint only
  session_items?: OffboardingSessionItem[]; // detail endpoint only
}

// --- Operational events (GET /events/{id}, POST /events/*) ---
export type EventPriority = "critical" | "high" | "normal" | "low";

export interface OperationalEvent {
  event_id: string;
  event_type: string;
  event_subtype?: string | null;
  asset_id?: string | null;
  site_id?: string | null;
  occurred_at: string;
  priority: EventPriority;
  payload: Record<string, unknown>;
  brief_id?: string | null;
  correlated_event_ids?: string[];
  acknowledged: boolean;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
}

export interface EventsResponse {
  items: OperationalEvent[];
  total: number;
  limit: number;
  offset: number;
}

// --- Plant state (GET /events/plant-state/{site_id}) ---
export type PlantOperatingState = "normal" | "turnaround" | "shutdown" | "emergency";

export interface PlantState {
  site_id: string;
  state: PlantOperatingState;
  /** Null when the site is on its configured default — nobody set it. */
  set_by?: string | null;
  set_at?: string | null;
  expires_at?: string | null;
}

// --- Governor state (GET /events/governor-state/{user_id}) ---
export interface GovernorEventState {
  user_id: string;
  push_count_last_hour: number;
  ceiling: number;
  state: GovernorStateValue;
  suppressed_count: number;
  next_delivery_allowed_at: string | null;
}

// --- Document pipeline status (GET /documents/{id}/status) ---
export type DocumentPipelineStage =
  | "queued" | "ocr" | "ner" | "graph_linking" | "indexing"
  | "complete" | "review_required" | "rejected" | "failed";

export interface DocumentStatus {
  document_id: string;
  stage: DocumentPipelineStage;
  updated_at: string;
  details?: string | null;
}

// --- P&ID topology (GET /documents/{id}/topology) ---
export interface TopologyNode {
  node_id: string;
  node_type: string;
  label: string;
  verification_status: "verified" | "unverified" | "disputed";
  properties?: Record<string, unknown>;
}

export interface TopologyEdge {
  edge_id: string;
  source_id: string;
  target_id: string;
  edge_type: string;
  label?: string;
}

export interface TopologyGraph {
  document_id: string;
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  generated_at: string;
  /** "vision_model" = extracted from the drawing. "demo_fixture" = the VLM was
   *  unreachable and the pipeline fell back to canned topology; the UI must say so. */
  topology_source?: "vision_model" | "demo_fixture";
  /** Drawing-level roll-up of element-by-element engineer verification (Layer 3 → Layer 7). */
  verification_status: "unverified" | "partially_verified" | "verified";
  elements_total: number;
  elements_verified: number;
  elements_disputed: number;
  safety_critical_total: number;
  safety_critical_verified: number;
  /** True only when every safety-critical element is confirmed and none are disputed.
   *  Until then the topology is a candidate, not canonical. */
  canonical_ready: boolean;
}

// --- Audit log (GET /audit-log) ---
export interface AuditLogEntry {
  log_id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  performed_by: string;
  /** Readable name when `performed_by` is a signed-in user. */
  performed_by_name?: string | null;
  timestamp: string;
  metadata?: Record<string, unknown> | null;
}

export interface AuditLogResponse {
  items: AuditLogEntry[];
  total: number;
}

// --- Health (GET /health/detailed) ---
export interface ServiceHealth {
  name: string;
  status: "healthy" | "degraded" | "down";
  latency_ms?: number | null;
  details?: string | null;
}

export interface HealthDetailed {
  overall: "healthy" | "degraded" | "down";
  services: ServiceHealth[];
  checked_at: string;
  /** Deployment phase actually being enforced by the backend (Layer 12), not a frontend
   *  build-time constant. Undefined only if the API predates the phase gate. */
  phase?: number;
  phase_enforced?: { synthesis: boolean; proactive_delivery: boolean };
}

// --- Audit pack (GET /compliance/audit-pack) — mirrors backend routers/compliance.py ---
export interface AuditPackEvidence {
  document_id: string;
  /** Vault file name, or "Promoted field input" for a promoted quarantine item. */
  title?: string | null;
  document_type: string | null;
  confidence: number | null;
  verification_status: string | null;
}

export interface AuditPackClause {
  clause_id: string;
  requirement_text: string | null;
  applies_to: string | null;
  authority_level: number;
  severity: string;
  evidence: AuditPackEvidence[];
  verified_evidence_count: number;
  clearance_blocked: boolean;
}

export interface AuditPack {
  framework: string;
  clauses: AuditPackClause[];
  total_clauses: number;
  total_evidence_docs: number;
  human_review_required: string[];
  note?: string;
  status?: string;
}

// --- OT instrumentation coverage (GET /assets/{asset_id}/ot-coverage) ---
export interface OtCoverage {
  asset_id: string;
  has_direct_sensors: boolean;
  sensor_tags: string[];
  /** "none" means no *verified* drawing establishes instrumentation — not a claim that the
   *  equipment has no sensors. "macro" is the brownfield case: equipment is on a verified
   *  drawing but no verified loop covers it, so only overall readings exist. */
  coverage_type: "direct" | "macro" | "none";
  verified_loops: number;
  total_loops: number;
  /** Provenance, so coverage can never be mistaken for a historian assertion. */
  derived_from: "verified_pid_topology";
  source_documents: string[];
  /** True when the drawing has instrumentation the engineer has not yet verified — the gap is
   *  review backlog, not absent instrumentation, and the UI should say so. */
  unverified_topology_present: boolean;
  last_reading?: string | null;
}

// --- Knowledge graph (Tasks 15-16) ---
export interface GraphNodeData {
  id: string;
  label: string;
  kind: string; // Asset | Event | Document | Concept | Person | Organization | …
  properties: Record<string, unknown>;
}

export interface GraphEdgeData {
  id: string;
  source: string;
  target: string;
  label: string;
  authority_level: number;
  verification_status: "verified" | "unverified" | "disputed" | "superseded";
  valid_from: string;
  valid_to: string; // "9999-…" sentinel = currently open
  document_id: string;
  confidence: number;
}

export interface KnowledgeGraphData {
  asset_id: string;
  as_of: string;
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  /** How many facts the backend withheld as test artifacts. Surfaced in the UI: a filtered view
   *  that does not say it is filtered is the same mistake that kept the linkage figure wrong. */
  excluded_test_documents: number;
}


/** One row of the knowledge-coverage matrix (`GET /assets/coverage`). Counts are DISTINCT by
 *  `edge_id` server-side, so a re-ingested asset does not look better covered than it is. */
export interface AssetCoverage {
  asset_id: string;
  name: string;
  equipment_class: string;
  criticality: string;
  facts: number;
  authoritative_facts: number;
  verified_facts: number;
  documents: number;
  pending_quarantine: number;
}
