"use client";

// SLA escalations — analytics arc: KPI strip → breakdown/composition charts →
// days-overdue distribution → merged drill-down table. One useFetch drives
// every zone: skeletons on first paint (no fixture flash — fixture fallback
// lives in api.ts) only when the fetcher actually fell back,
// error + retry on every surface.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ChartContainer } from "@/components/charts";
import { DataTable, EmptyState, FilterTabs, MetricCard, PageHeader } from "@/components/ui";
import { getSlaReport } from "@/lib/api";
import { fmtRelTime } from "@/lib/format";
import { useReducedMotion } from "@/lib/motion";
import { useFetch } from "@/lib/use-fetch";
import { nowMs } from "@/lib/utils";
import { buildRows, COLUMNS, type SlaRow } from "./_components/columns";
import { mixDonut, rankedBars, type CountRow } from "./_components/plots";

import { Icon } from "@/components/icon";
const BUCKETS = [
  { label: "0–1d", max: 1 },
  { label: "1–3d", max: 3 },
  { label: "3–7d", max: 7 },
  { label: "7–14d", max: 14 },
  { label: "14d+", max: Infinity },
] as const;

export default function SlaPage() {
  const state = useFetch(getSlaReport);
  const router = useRouter();
  const reduced = useReducedMotion();
  const [filter, setFilter] = useState("all");

  const loading = state.status === "loading";
  const report = state.status === "live" ? state.data : null;
  const errorMsg = state.status === "error" ? state.error.message : undefined;
  const retry = state.status === "error" ? state.retry : undefined;

  const rows = useMemo(() => (report ? buildRows(report, nowMs()) : []), [report]);

  const breakdown = useMemo<CountRow[]>(() => {
    const counts = new Map<string, CountRow>();
    for (const r of rows) {
      const entry = counts.get(`${r.kind}:${r.category}`) ?? {
        label: r.category,
        value: 0,
        tone: r.kind === "conflict" ? ("danger" as const) : ("caution" as const),
      };
      entry.value += 1;
      counts.set(`${r.kind}:${r.category}`, entry);
    }
    return [...counts.values()].sort((a, b) => b.value - a.value);
  }, [rows]);

  const histogram = useMemo<CountRow[]>(
    () =>
      BUCKETS.map(({ label, max }, i) => ({
        label,
        value: rows.filter((r) => r.days_overdue < max && r.days_overdue >= (BUCKETS[i - 1]?.max ?? 0)).length,
      })),
    [rows],
  );

  // Defensive totals: a partial live payload must never crash the render.
  const conflicts = report?.overdue_conflicts ?? [];
  const quarantine = report?.overdue_quarantine_items ?? [];
  const conflictsTotal = report ? (report.overdue_conflicts_total ?? conflicts.length) : null;
  const quarantineTotal = report ? (report.overdue_quarantine_total ?? quarantine.length) : null;
  const escalated = report?.escalated_this_run ?? null;

  const donut = useMemo<CountRow[]>(
    () =>
      [
        { label: "Conflicts", value: conflictsTotal ?? 0, tone: "danger" as const },
        { label: "Quarantine", value: quarantineTotal ?? 0, tone: "caution" as const },
      ].filter((d) => d.value > 0),
    [conflictsTotal, quarantineTotal],
  );

  const visible = useMemo(
    () => (filter === "all" ? rows : rows.filter((r) => r.kind === filter)),
    [rows, filter],
  );

  return (
    <div data-testid="sla-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/governance" className="inline-flex items-center gap-1.5 text-body text-muted transition-colors hover:text-ink">
        <Icon name="caret-left" size={15} />
        Governance
      </Link>

      <PageHeader
        className="mt-4"
        title="SLA Escalations"
        lede="Where review deadlines have been missed right now. Conflicts and quarantine items that are past their decision window are listed here and escalated, with how long each has been waiting."
      />
      {report && <p className="mt-2 text-caption text-muted">Checked {fmtRelTime(report.checked_at)}</p>}

      {/* KPI strip — overdue tones flip to verified at zero */}
      <div data-testid="sla-summary" className="mt-5 mesh stagger grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Overdue conflicts" value={conflictsTotal} sub="past decision deadline" loading={loading} href="/governance/conflicts" tone={conflictsTotal === null ? "neutral" : conflictsTotal === 0 ? "verified" : "danger"} />
        <MetricCard label="Overdue quarantine" value={quarantineTotal} sub="past review window" loading={loading} href="/governance/quarantine" tone={quarantineTotal === null ? "neutral" : quarantineTotal === 0 ? "verified" : "danger"} />
        <MetricCard label="Escalated conflicts" value={escalated?.conflicts ?? null} sub="this run" loading={loading} tone={escalated?.conflicts ? "caution" : "neutral"} />
        <MetricCard label="Escalated quarantine" value={escalated?.quarantine_items ?? null} sub="this run" loading={loading} tone={escalated?.quarantine_items ? "caution" : "neutral"} />
      </div>

      {/* Breakdown + composition */}
      <div data-testid="sla-charts" className="mt-6 grid gap-6 lg:grid-cols-2">
        <ChartContainer title="Overdue by category" sub="Conflicts by track, quarantine by input type" height={240} collapsible loading={loading} error={errorMsg} onRetry={retry} empty={!loading && !errorMsg && breakdown.length === 0 && "No overdue items."}>
          {rankedBars(breakdown, !reduced)}
        </ChartContainer>
        <ChartContainer title="Conflicts vs quarantine" sub="Share of the overdue backlog" height={240} collapsible loading={loading} error={errorMsg} onRetry={retry} empty={!loading && !errorMsg && donut.length === 0 && "No overdue items."}>
          {mixDonut(donut, !reduced)}
        </ChartContainer>
      </div>

      {/* Distribution — the honest time dimension for an escalation-only endpoint */}
      <div className="mt-6">
        <ChartContainer title="Days overdue" sub="How stale the breaches are" height={200} collapsible loading={loading} error={errorMsg} onRetry={retry} empty={!loading && !errorMsg && rows.length === 0 && "No overdue items."}>
          {rankedBars(histogram, !reduced)}
        </ChartContainer>
      </div>

      {/* Drill-down — merged queues, filterable, sortable, paginated */}
      <div data-testid="sla-table" className="mt-6">
        <DataTable<SlaRow>
          columns={COLUMNS}
          rows={visible}
          keyFn={(r) => `${r.kind}-${r.id}`}
          pageSize={25}
          loading={loading}
          onRowClick={(r) => router.push(r.href)}
          toolbar={
            <FilterTabs
              tabs={[
                { key: "all", label: "All", count: rows.length },
                { key: "conflict", label: "Conflicts", count: conflicts.length },
                { key: "quarantine", label: "Quarantine", count: quarantine.length },
              ]}
              active={filter}
              onChange={setFilter}
            />
          }
          emptyState={
            errorMsg ? (
              <EmptyState message={`Couldn't load the SLA report — ${errorMsg}`} action={retry ? { label: "Retry", onClick: retry } : undefined} />
            ) : (
              <EmptyState message={rows.length > 0 ? "No items match this filter." : "All SLAs on time ✓"} />
            )
          }
        />
      </div>
    </div>
  );
}
