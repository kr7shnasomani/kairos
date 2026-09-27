"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { MocItem } from "@/lib/types";
import { getMocList } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { relativeTime } from "@/lib/utils";
import { Button, DataTable, EmptyState, FilterTabs, PageHeader, StatusBadge, type TableColumn } from "@/components/ui";
import { StatPills } from "@/components/stat-pills";

import { Icon } from "@/components/icon";
/** MocItem re-mapped so it satisfies DataTable's Record constraint. */
type MocRow = Pick<MocItem, keyof MocItem>;

const STATUS_TONE: Record<string, "caution" | "verified" | "danger"> = {
  pending: "caution",
  draft: "caution",
  pending_approval: "caution",
  approved: "verified",
  rejected: "danger",
};

// Backend MoC lifecycle: draft → pending_approval → approved | rejected. Auto-drafted EWR
// items sit in `draft`/`pending_approval` awaiting engineering sign-off — both read as
// "pending review" to a reviewer, so the Pending view groups them together.
const PENDING_STATUSES = new Set(["pending", "draft", "pending_approval"]);

// Built lazily (mount-once useState initializer) — no Date.now() at module scope.
const COLUMNS: TableColumn<MocRow>[] = [
  { key: "moc_id", label: "Change", sortable: true, render: (r) => <span className="tabular whitespace-nowrap font-semibold text-accent">{r.moc_id}</span> },
  {
    key: "parameter", label: "Discrepancy", className: "w-[38%]",
    render: (r) => (
      <span className="block min-w-0">
        <span className="block truncate font-medium text-ink" title={r.description ?? undefined}>
          {r.parameter ? r.parameter.replace(/_/g, " ") : (r.description ?? "—")}
        </span>
        {(r.source_a || r.source_b) && (
          <span className="tabular block truncate text-label text-muted">{String(r.source_a?.value ?? "—")} vs {String(r.source_b?.value ?? "—")}</span>
        )}
      </span>
    ),
  },
  { key: "asset_id", label: "Asset", render: (r) => <span className="tabular text-caption font-medium text-accent">{r.asset_id ?? "—"}</span> },
  {
    key: "blast_radius_count", label: "Blast radius", sortValue: (r) => r.blast_radius_count ?? 0,
    render: (r) => <span className={`tabular ${(r.blast_radius_count ?? 0) > 0 ? "font-semibold text-danger" : "text-muted"}`}>{r.blast_radius_count ?? 0}</span>,
  },
  { key: "status", label: "Status", sortable: true, render: (r) => <StatusBadge tone={STATUS_TONE[r.status] ?? "neutral"}>{r.status}</StatusBadge> },
  {
    key: "created_at", label: "Age", sortValue: (r) => Date.parse(r.created_at),
    render: (r) => <span className="tabular whitespace-nowrap text-caption text-muted" title={r.created_at}>{relativeTime(r.created_at)}</span>,
  },
];

export default function MocListPage() {
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState("pending");

  // Spec §5: params unchanged — same zero-arg getMocList() call as before.
  const state = useFetch(() => getMocList(), []);
  const loading = state.status === "loading";
  const hasData = state.status === "live";
  const fetched = hasData ? state.data.items ?? [] : [];
  // An empty live list is a valid state ("No changes under review"). This used to swap in
  // buildFixture() — fabricated MOC-2024-001 rows with invented document IDs — whenever the
  // real list came back empty, i.e. on a *successful* request.
  const items = fetched;

  const counts = useMemo(() => ({
    pending: items.filter((m) => PENDING_STATUSES.has(m.status)).length,
    approved: items.filter((m) => m.status === "approved").length,
    rejected: items.filter((m) => m.status === "rejected").length,
  }), [items]);

  const rows = useMemo<MocRow[]>(
    () =>
      statusFilter === "all"
        ? items
        : statusFilter === "pending"
          ? items.filter((m) => PENDING_STATUSES.has(m.status))
          : items.filter((m) => m.status === statusFilter),
    [items, statusFilter],
  );

  return (
    <div data-testid="moc-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/governance" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <Icon name="caret-left" size={15} />
        Governance
      </Link>

      <PageHeader
        className="mt-4"
        eyebrow="Governance"
        title="Management of Change"
        lede="Auto-drafted EWR items for engineering-track conflicts. Approval here closes the validity window of the superseded edge and clears any affected downstream facts."
      />

      <section data-testid="moc-summary" className="mt-5">
        <StatPills
          loading={loading}
          pills={[
            { key: "pending", label: "Pending", value: counts.pending },
            { key: "approved", label: "Approved", value: counts.approved },
            { key: "rejected", label: "Rejected", value: counts.rejected, tone: "danger" },
          ]}
        />
      </section>

      <section data-testid="moc-filters" className="mt-4 flex flex-wrap items-center gap-3">
        <FilterTabs
          tabs={[
            { key: "all", label: "All" },
            { key: "pending", label: "Pending", count: counts.pending },
            { key: "approved", label: "Approved" },
            { key: "rejected", label: "Rejected" },
          ]}
          active={statusFilter}
          onChange={setStatusFilter}
        />
      </section>

      <section data-testid="moc-register" className="mt-4">
        {state.status === "error" ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-line bg-surface px-4 py-10 text-center">
            <p className="text-body text-muted">Could not load the change register.</p>
            <Button variant="primary" onClick={state.retry}>Retry</Button>
          </div>
        ) : (
          <DataTable<MocRow>
            key={statusFilter}
            columns={COLUMNS}
            rows={rows}
            keyFn={(r) => r.moc_id}
            pageSize={25}
            loading={loading}
            onRowClick={(r) => router.push(`/governance/moc/${r.moc_id}`)}
            emptyState={<EmptyState message="No changes under review" />}
          />
        )}
      </section>
    </div>
  );
}
