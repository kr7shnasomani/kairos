"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { getConflicts, getQuarantine, getEvents } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { relativeTime } from "@/lib/utils";
import { Button, ButtonLink, DataTable, EmptyState, FilterTabs, PageHeader, StatusBadge, type TableColumn } from "@/components/ui";
import { StatPills } from "@/components/stat-pills";

import { Icon } from "@/components/icon";
type NcSource = "conflict" | "inspection" | "dispute";

interface Nc extends Record<string, unknown> {
  id: string;
  source: NcSource;
  asset_id: string | null;
  title: string;
  detail: string;
  tone: "danger" | "caution";
  when: string;
  origin: { href: string; label: string };
}

const SOURCE_LABEL: Record<NcSource, string> = {
  conflict: "Knowledge conflict",
  inspection: "Failed inspection",
  dispute: "Disputed input",
};

const COLUMNS: TableColumn<Nc>[] = [
  {
    key: "title", label: "Issue", className: "min-w-[180px]",
    render: (r) => (
      <span className="block min-w-0">
        <StatusBadge tone={r.tone}>{SOURCE_LABEL[r.source]}</StatusBadge>
        <span className="mt-1 block truncate font-semibold text-ink">{r.title}</span>
      </span>
    ),
  },
  {
    key: "tone", label: "Severity", sortValue: (r) => (r.tone === "danger" ? 0 : 1),
    render: (r) => <span className={`whitespace-nowrap text-caption font-semibold ${r.tone === "danger" ? "text-danger" : "text-caution"}`}>{r.tone === "danger" ? "Urgent" : "Attention"}</span>,
  },
  {
    key: "detail", label: "Finding", className: "w-[38%]",
    render: (r) => <span className="block truncate text-caption text-muted" title={r.detail}>{r.detail}</span>,
  },
  {
    key: "asset_id", label: "Asset",
    render: (r) => r.asset_id
      ? <Link href={`/assets/${r.asset_id}`} className="tabular whitespace-nowrap text-caption font-medium text-accent hover:underline">{r.asset_id}</Link>
      : <span className="text-muted">—</span>,
  },
  {
    key: "when", label: "Raised", sortValue: (r) => Date.parse(r.when),
    render: (r) => <span className="tabular whitespace-nowrap text-caption text-muted" title={r.when}>{relativeTime(r.when)}</span>,
  },
  {
    key: "origin", label: "Source",
    render: (r) => <Link href={r.origin.href} className="whitespace-nowrap text-caption text-accent hover:underline">Open {r.origin.label.toLowerCase()} ↗</Link>,
  },
  {
    key: "rca", label: "Actions",
    render: () => (
      <ButtonLink aria-label="Root-cause analysis" href="/rca" className="h-8 whitespace-nowrap px-3 text-caption">
        Open RCA
      </ButtonLink>
    ),
  },
];

export default function NonConformancePage() {
  const [filter, setFilter] = useState<"all" | NcSource>("all");

  // Spec §5: same three fetchers, identical params, composed in one useFetch.
  const state = useFetch(async () => {
    const [c, q, e] = await Promise.all([getConflicts(), getQuarantine(), getEvents({ limit: 50 })]);
    return {
      data: { conflicts: c.data.items ?? [], quarantine: q.data.items ?? [], events: e.data.items ?? [] },
      source: "live" as const,
    };
  }, []);
  const loading = state.status === "loading";
  const hasData = state.status === "live";

  const items = useMemo<Nc[]>(() => {
    if (!hasData) return [];
    const { conflicts, quarantine, events } = state.data;
    const ncs: Nc[] = [];
    for (const cf of conflicts) {
      if (cf.status === "resolved") continue;
      ncs.push({
        id: cf.conflict_id, source: "conflict", asset_id: cf.asset_id,
        title: `Conflict on ${cf.parameter}`,
        detail: `${cf.track} track, severity ${cf.severity}`,
        tone: cf.severity === "safety_critical" || cf.is_overdue ? "danger" : "caution",
        when: cf.created_at,
        origin: { href: "/governance/conflicts", label: "Conflict" },
      });
    }
    for (const qi of quarantine) {
      if (qi.review_status !== "disputed") continue;
      ncs.push({
        id: qi.item_id, source: "dispute", asset_id: qi.asset_id,
        title: "Disputed field input", detail: qi.content.slice(0, 80),
        tone: "caution", when: qi.submitted_at,
        origin: { href: "/governance/quarantine", label: "Quarantine" },
      });
    }
    for (const ev of events) {
      const payload = (ev.payload ?? {}) as Record<string, unknown>;
      if (ev.event_type !== "inspection_complete" || String(payload.result ?? "") !== "failed") continue;
      ncs.push({
        id: ev.event_id, source: "inspection", asset_id: ev.asset_id ?? null,
        title: "Inspection failed", detail: String(payload.findings ?? "See event"),
        tone: "danger", when: ev.occurred_at,
        origin: { href: `/events/${ev.event_id}`, label: "Event" },
      });
    }
    return ncs.sort((a, b) => (a.when < b.when ? 1 : -1));
  }, [state, hasData]);

  const counts = useMemo(() => ({
    conflict: items.filter((i) => i.source === "conflict").length,
    inspection: items.filter((i) => i.source === "inspection").length,
    dispute: items.filter((i) => i.source === "dispute").length,
    urgent: items.filter((i) => i.tone === "danger").length,
  }), [items]);

  const rows = filter === "all" ? items : items.filter((i) => i.source === filter);

  return (
    <div data-testid="nonconformance-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/compliance" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <Icon name="caret-left" size={15} />
        Compliance
      </Link>

      <PageHeader
        className="mt-4"
        title="Non-Conformance Tracking"
        lede="Open non-conformances composed from unresolved conflicts, failed inspections, and disputed field inputs. Each links to its root-cause workspace and originating record."
      />

      <section data-testid="nonconformance-summary" className="mt-5">
        <StatPills
          loading={loading}
          pills={[
            { key: "open", label: "Open", value: items.length },
            { key: "urgent", label: "Urgent", value: counts.urgent, tone: "danger" },
            { key: "attention", label: "Attention", value: items.length - counts.urgent },
          ]}
        />
      </section>

      <section data-testid="nonconformance-filters" className="mt-4 flex flex-wrap items-center gap-3">
        <FilterTabs
          tabs={[
            { key: "all", label: "All", count: items.length },
            { key: "conflict", label: "Conflicts", count: counts.conflict },
            { key: "inspection", label: "Inspections", count: counts.inspection },
            { key: "dispute", label: "Disputes", count: counts.dispute },
          ]}
          active={filter}
          onChange={(k) => setFilter(k as "all" | NcSource)}
        />
        <span className="tabular ml-auto text-caption font-medium text-muted">{rows.length} of {items.length}</span>
      </section>

      <section data-testid="nonconformance-queue" className="mt-4">
        {state.status === "error" ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-line bg-surface px-4 py-10 text-center">
            <p className="text-body text-muted">Could not load non-conformances.</p>
            <Button variant="primary" onClick={state.retry}>Retry</Button>
          </div>
        ) : (
          <DataTable<Nc>
            key={filter}
            columns={COLUMNS}
            rows={rows}
            keyFn={(r) => `${r.source}-${r.id}`}
            pageSize={25}
            loading={loading}
            emptyState={<EmptyState message="No nonconformances open ✓" />}
          />
        )}
      </section>
    </div>
  );
}
