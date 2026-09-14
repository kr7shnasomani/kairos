// Audit-pack assembly — evidence organised by regulatory clause for a chosen framework.
"use client";

import Link from "next/link";
import { useState } from "react";
import type { AuditPackClause } from "@/lib/types";
import { getAuditPack } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { fmtPct } from "@/lib/format";
import { Button, DataTable, EmptyState, FilterTabs, PageHeader, StatusBadge, type TableColumn } from "@/components/ui";
import { StatPills } from "@/components/stat-pills";

// `key` must match the framework value stored on Neo4j regulation nodes (underscored);
// `label` is the human-facing display. Only frameworks actually seeded in the graph are
// listed — see GET /compliance/frameworks → configured_frameworks (OISD_117, ISO_45001).
const FRAMEWORKS = [
  { key: "OISD_117", label: "OISD-117" },
  { key: "ISO_45001", label: "ISO 45001" },
];

/** AuditPackClause re-mapped so it satisfies DataTable's Record constraint. */
type ClauseRow = Pick<AuditPackClause, keyof AuditPackClause>;

function minConfidence(c: ClauseRow): number | null {
  const values = (c.evidence ?? []).map((e) => e.confidence).filter((v): v is number => v != null);
  return values.length ? Math.min(...values) : null;
}

function buildColumns(framework: string): TableColumn<ClauseRow>[] {
  return [
    { key: "clause_id", label: "Clause", sortable: true, render: (r) => <span className="tabular whitespace-nowrap font-semibold text-accent">{framework} §{r.clause_id}</span> },
    {
      key: "requirement_text", label: "Requirement", className: "w-[38%]",
      render: (r) => (
        <span className="block min-w-0">
          <span className="block truncate text-ink" title={r.requirement_text ?? undefined}>{r.requirement_text ?? "—"}</span>
          {r.applies_to && <span className="block truncate text-label text-muted">Applies to {r.applies_to}</span>}
        </span>
      ),
    },
    {
      key: "evidence", label: "Evidence", sortValue: (r) => r.evidence?.length ?? 0,
      render: (r) => {
        const docs = r.evidence ?? [];
        return (
          <span className="block min-w-0 whitespace-nowrap">
            <span className="tabular text-caption text-ink">{r.verified_evidence_count ?? 0}/{docs.length} verified</span>
            <span className="block">
              {docs.slice(0, 2).map((e, i) => (
                <Link key={e.document_id} href={`/documents/${e.document_id}`} className="tabular text-label text-accent hover:underline">
                  {i > 0 && ", "}{e.title ?? e.document_id}
                </Link>
              ))}
              {docs.length > 2 && <span className="tabular text-label text-muted"> +{docs.length - 2}</span>}
              {docs.length === 0 && <span className="text-label text-danger">No supporting evidence</span>}
            </span>
          </span>
        );
      },
    },
    {
      key: "confidence", label: "Confidence", sortValue: (r) => minConfidence(r) ?? -1,
      render: (r) => {
        const min = minConfidence(r);
        return <span className="tabular whitespace-nowrap text-caption text-muted">{min == null ? "—" : fmtPct(min)}</span>;
      },
    },
    {
      key: "clearance_blocked", label: "Status", sortValue: (r) => (r.clearance_blocked ? 0 : 1),
      // Never "Cleared": the pack is a draft and clearance is a human attestation (see the note above
      // the table). It said "Cleared" for clauses whose evidence was 0/7 verified.
      render: (r) => r.clearance_blocked
        ? <StatusBadge tone="caution">Requires human review</StatusBadge>
        : <StatusBadge tone="info">Ready for sign-off</StatusBadge>,
    },
  ];
}

export default function AuditPackPage() {
  const [framework, setFramework] = useState(FRAMEWORKS[0].key);
  const frameworkLabel = FRAMEWORKS.find((f) => f.key === framework)?.label ?? framework;
  // Spec §5: params unchanged — same getAuditPack(framework) call, refetch on change.
  const state = useFetch(() => getAuditPack(framework), [framework]);
  const loading = state.status === "loading";
  const pack = state.status === "live" ? state.data : null;

  const clauses: ClauseRow[] = pack?.clauses ?? [];
  const reviewNeeded = clauses.filter((c) => c.clearance_blocked).length;

  return (
    <div data-testid="audit-pack-workspace" className="mx-auto max-w-[1400px] print:max-w-none">
      <div className="print:hidden">
        <Link href="/compliance" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M15 18l-6-6 6-6" />
          </svg>
          Compliance
        </Link>
      </div>

      <PageHeader
        compact
        className="mt-4"
        eyebrow="Layer 11 · Audit preparation"
        title="Audit-pack assembly"
        lede="Evidence organised by regulatory clause. This accelerates audit preparation; it is not automated compliance. Clauses below the confidence threshold are blocked and require human sign-off."
        actions={
          <>
            <Button variant="ghost" onClick={() => window.print()} className="print:hidden">
              Print / export PDF
            </Button>
          </>
        }
      />

      <section data-testid="audit-pack-summary" className="mt-5 print:hidden">
        <StatPills
          loading={loading}
          pills={[
            { key: "clauses", label: "Clauses", value: pack?.total_clauses ?? 0 },
            { key: "evidence", label: "Evidence documents", value: pack?.total_evidence_docs ?? 0 },
            { key: "review", label: "Human review", value: reviewNeeded, tone: "danger" },
          ]}
        />
      </section>

      <section data-testid="audit-pack-controls" className="mt-4 flex flex-wrap items-center gap-3 print:hidden">
        <FilterTabs
          tabs={FRAMEWORKS.map((f) => ({ key: f.key, label: f.label }))}
          active={framework}
          onChange={setFramework}
        />
        <span className="text-label text-muted">Human attestation is required; this view does not clear a clause.</span>
      </section>

      <section data-testid="audit-pack-clauses" className="mt-4">
        {state.status === "error" ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-line bg-surface px-4 py-10 text-center">
            <p className="text-body text-muted">Could not assemble the audit pack.</p>
            <Button variant="primary" onClick={state.retry}>Retry</Button>
          </div>
        ) : (
          <DataTable<ClauseRow>
            key={framework}
            columns={buildColumns(frameworkLabel)}
            rows={clauses}
            keyFn={(r) => r.clause_id}
            pageSize={25}
            loading={loading}
            emptyState={<EmptyState message="No audit packs generated" action={{ label: "Ingest a document", href: "/documents/ingest" }} />}
          />
        )}
      </section>
    </div>
  );
}
