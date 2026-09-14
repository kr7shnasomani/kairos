"use client";

import { useMemo, useState } from "react";
import type { AuditLogEntry } from "@/lib/types";
import { getAuditLog } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { Button, DataTable, EmptyState, FilterTabs, PageHeader, StatusBadge, Timestamp, type TableColumn } from "@/components/ui";

/** AuditLogEntry re-mapped so it satisfies DataTable's Record constraint. */
type AuditRow = Pick<AuditLogEntry, keyof AuditLogEntry>;

const ACTION_TONE: Record<string, "danger" | "caution" | "verified" | "info" | "neutral"> = {
  sla_escalated: "danger",
  quarantine_disputed: "danger",
  // Cross-source clock skew (services/timestamp_alignment.py) — a real inconsistency.
  timestamp_drift_detected: "caution",
  // Ingest lag: the document was written long before it was uploaded. Historical documents do
  // that legitimately, so this is an observation, not a warning — `valid_from` still uses the
  // source timestamp. Kept distinct from drift above on purpose; the pipeline used to conflate
  // the two and overwrite the true date.
  ingest_lag_recorded: "info",
  attribution_flag: "caution",
  circuit_breaker_override: "caution",
  recurring_failure_detected: "caution",
  deviation_flag_raised: "caution",
  brief_acknowledged: "verified",
  quarantine_promoted: "verified",
  moc_resolved: "verified",
  asset_created: "verified",
  document_ingested: "info",
  rca_pack_generated: "info",
  synthesis: "info",
  model_gate_result: "info",
  offboarding_programme_created: "info",
};

const pretty = (t: string) => t.replace(/_/g, " ");
const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

// A compact, human-readable one-liner per audit action — fills the Details
// column with the key facts of each record instead of a bare metadata toggle.
function summarizeMeta(action: string, meta: Record<string, unknown> | null): string | null {
  if (!meta) return null;
  const m = meta as Record<string, unknown>;
  const parts: string[] = [];
  const push = (v: unknown) => { if (v !== null && v !== undefined && v !== "") parts.push(String(v)); };

  switch (action) {
    case "model_gate_result":
      push(m.model_name);
      if (typeof m.f1 === "number") push(`F1 ${m.f1.toFixed(2)}`);
      if (m.passed !== undefined) push(m.passed ? "passed" : "failed");
      break;
    case "synthesis":
      if (m.query) push(`"${String(m.query).slice(0, 48)}"`);
      push(m.refused ? "refused · safety gate" : "answered");
      if (m.query_category) push(pretty(String(m.query_category)));
      break;
    case "sla_escalated":
      push(m.asset_id);
      if (m.input_type) push(pretty(String(m.input_type)));
      if (m.escalated_to) push(`→ ${pretty(String(m.escalated_to))}`);
      break;
    case "document_ingested":
      push(m.file_name);
      if (m.document_type) push(pretty(String(m.document_type)));
      if (m.authority_level) push(`L${m.authority_level}`);
      break;
    case "asset_created":
      push(m.tag_number);
      push(m.eam_source);
      break;
    case "offboarding_programme_created":
      push(m.personnel_email);
      if (m.total_sessions) push(`${m.total_sessions} sessions`);
      break;
    case "deviation_flag_raised":
      push(m.asset_id);
      push(m.affected_topology_path);
      break;
  }

  // Generic fallback: first few scalar fields.
  if (parts.length === 0) {
    for (const [k, v] of Object.entries(m)) {
      if (v === null || typeof v === "object") continue;
      parts.push(`${pretty(k)} ${v}`);
      if (parts.length >= 3) break;
    }
  }
  return parts.length ? parts.join(" · ") : null;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Some entities key on a raw UUID (quarantine items, queries, offboarding
// sessions), which reads as noise next to the DOC-/asset-/model ids that are
// already legible. Derive a human label from the metadata so the column is
// consistent. The full id stays in the title tooltip and the entity-ID filter.
function entityLabel(r: AuditRow): { primary: string; secondary: string } {
  const id = r.entity_id == null ? "" : String(r.entity_id);
  const type = cap(pretty(r.entity_type));
  // Opaque = a bare UUID or no id at all (e.g. synthesis queries) → derive a label.
  const isOpaque = id === "" || UUID_RE.test(id);
  if (!isOpaque) return { primary: id, secondary: type };
  const m = (r.metadata ?? {}) as Record<string, unknown>;
  // Short identifiers only — not free text like a query (that would read as a
  // sentence in the Entity column; the query text is already in the Details column).
  const friendly =
    (typeof m.asset_id === "string" && m.asset_id) ||
    (typeof m.personnel_email === "string" && m.personnel_email) ||
    (typeof m.tag_number === "string" && m.tag_number) ||
    "";
  return friendly
    ? { primary: String(friendly), secondary: type }
    : { primary: type, secondary: id ? `#${id.slice(0, 8)}` : "" };
}

const COLUMNS: TableColumn<AuditRow>[] = [
  {
    key: "timestamp", label: "Recorded", sortValue: (r) => Date.parse(r.timestamp),
    className: "w-[12%]",
    render: (r) => <Timestamp value={r.timestamp} />,
  },
  {
    key: "action", label: "Action", sortable: true,
    className: "w-[16%]",
    render: (r) => <StatusBadge tone={ACTION_TONE[r.action] ?? "neutral"} dot={false}>{pretty(r.action)}</StatusBadge>,
  },
  {
    key: "entity_id", label: "Entity", sortable: true,
    className: "w-[22%]",
    render: (r) => {
      const { primary, secondary } = entityLabel(r);
      return (
        <span className="block min-w-0">
          <span className="block truncate font-semibold text-ink" title={r.entity_id ? String(r.entity_id) : primary}>{primary}</span>
          <span className="block text-label text-muted">{secondary}</span>
        </span>
      );
    },
  },
  {
    key: "performed_by", label: "Performed by", sortable: true,
    className: "w-[15%]",
    render: (r) => (
      <span className="block min-w-0">
        <span className="block truncate font-medium text-ink" title={String(r.performed_by)}>{r.performed_by_name ?? r.performed_by}</span>
        <span className="tabular-nums block truncate text-label text-muted">{r.log_id}</span>
      </span>
    ),
  },
  {
    key: "metadata", label: "Details",
    // No explicit width — fills the remaining ~41% with the readable summary.
    render: (r) => {
      const meta = (r.metadata ?? null) as Record<string, unknown> | null;
      if (!meta || Object.keys(meta).length === 0) return <span className="text-muted">—</span>;
      const summary = summarizeMeta(r.action, meta);
      return (
        <div className="min-w-0">
          {summary && <span className="block truncate text-caption text-ink" title={summary}>{summary}</span>}
          <details onClick={(e) => e.stopPropagation()} className="mt-0.5">
            <summary className="cursor-pointer list-none text-label font-medium text-link transition-colors hover:opacity-80">Raw metadata</summary>
            <pre className="mt-1 max-w-full overflow-x-auto rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-label text-muted">{JSON.stringify(meta, null, 2)}</pre>
          </details>
        </div>
      );
    },
  },
];

export default function AuditPage() {
  const [entityTypeFilter, setEntityTypeFilter] = useState("all");
  const [entityId, setEntityId] = useState("");
  const [entityIdInput, setEntityIdInput] = useState("");

  const state = useFetch(() => getAuditLog({ entity_id: entityId || undefined, limit: 100 }), [entityId]);
  const loading = state.status === "loading";
  const entries = useMemo<AuditRow[]>(() => (state.status === "live" ? state.data.items ?? [] : []), [state]);

  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of entries) counts[e.entity_type] = (counts[e.entity_type] ?? 0) + 1;
    return counts;
  }, [entries]);

  // Derived from the real data — every entity type present is filterable, so the
  // tab counts always add up to the record total (no stale hard-coded set).
  const entityTypes = useMemo(
    () => Object.keys(typeCounts).sort((a, b) => typeCounts[b] - typeCounts[a]),
    [typeCounts],
  );

  const rows = useMemo(
    () => (entityTypeFilter === "all" ? entries : entries.filter((e) => e.entity_type === entityTypeFilter)),
    [entries, entityTypeFilter],
  );

  const exportHref = `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(rows, null, 2))}`;

  return (
    <div data-testid="audit-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader
        eyebrow="Layer 7–8 · Immutable record"
        title="Audit Trail"
        lede="Every governance decision, delivery, ingestion, and model-gate result, in chronological order. Immutable by design."
        actions={
          <a
            href={exportHref}
            download="kairos-audit-log.json"
            className="inline-flex h-9 items-center rounded-lg border border-line px-3.5 text-caption font-semibold text-ink transition-colors hover:bg-surface-2"
          >
            Export JSON
          </a>
        }
      />

      <section data-testid="audit-entries" className="mt-4">
        {state.status === "error" ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-line bg-surface px-4 py-10 text-center">
            <p className="text-body text-muted">Could not load the audit trail.</p>
            <Button variant="primary" onClick={state.retry}>Retry</Button>
          </div>
        ) : (
          <DataTable<AuditRow>
            key={entityTypeFilter}
            columns={COLUMNS}
            rows={rows}
            keyFn={(r) => r.log_id}
            pageSize={25}
            loading={loading}
            emptyState={<EmptyState message="No audit activity" />}
            toolbar={
              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
                <FilterTabs
                  tabs={[
                    { key: "all", label: "All", count: entries.length },
                    ...entityTypes.map((t) => ({ key: t, label: cap(pretty(t)), count: typeCounts[t] })),
                  ]}
                  active={entityTypeFilter}
                  onChange={setEntityTypeFilter}
                />
                <form
                  className="flex min-w-0 flex-1 items-center gap-2 sm:justify-end"
                  onSubmit={(e) => { e.preventDefault(); setEntityId(entityIdInput.trim()); }}
                >
                  <input
                    value={entityIdInput}
                    onChange={(e) => setEntityIdInput(e.target.value)}
                    placeholder="Filter by entity ID…"
                    aria-label="Filter by entity ID"
                    className="tabular h-9 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-caption outline-none transition-colors focus:border-accent sm:max-w-64"
                  />
                  <button type="submit" className="inline-flex h-9 items-center rounded-lg border border-line px-3 text-caption font-semibold text-muted transition-colors hover:bg-surface-2 hover:text-ink">
                    Search
                  </button>
                  {entityId && (
                    <button type="button" onClick={() => { setEntityId(""); setEntityIdInput(""); }} className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg text-caption text-muted hover:bg-surface-2 hover:text-ink" aria-label="Clear search">✕</button>
                  )}
                </form>
              </div>
            }
          />
        )}
      </section>
    </div>
  );
}
