// Compliance hub — where are compliance gaps concentrated, and how severe?
// KPI strip → framework ranking + severity mix → paginated gap register → workflow links.
"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { BarList } from "@/components/charts/bar-list";
import { Donut } from "@/components/charts/donut";
import { ChartSkeleton } from "@/components/skeleton";
import { DataTable, EmptyState, FilterTabs, MetricCard, PageHeader, StatusBadge, type TableColumn } from "@/components/ui";
import { Card } from "@/components/ui-card";
import { getComplianceDashboard, getComplianceGaps, type Fetched } from "@/lib/api";
import { fmtRelTime } from "@/lib/format";
import type { ComplianceDashboard, ComplianceGap, GapSeverity } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";

// Pick-mapped so the interface satisfies DataTable's Record constraint.
type GapRow = Pick<ComplianceGap, keyof ComplianceGap>;

const SEV_TONE: Record<GapSeverity, "danger" | "caution" | "info"> = { critical: "danger", major: "caution", minor: "info" };
const SEV_RANK: Record<GapSeverity, number> = { critical: 0, major: 1, minor: 2 };

const fwLabel = (fw: string) => fw.replace(/_/g, "-");

const truncate = (text: string | null | undefined, width: string) =>
  text ? <span title={text} className={`block truncate ${width}`}>{text}</span> : "—";

const COLUMNS: TableColumn<GapRow>[] = [
  { key: "framework", label: "Framework", sortable: true, render: (g) => <span className="tabular font-semibold text-ink">{fwLabel(g.framework)}</span> },
  { key: "clause_id", label: "Clause", render: (g) => <span className="tabular text-muted">§{g.clause_id}</span> },
  {
    key: "asset",
    label: "Asset",
    render: (g) => (
      <Link href={`/assets/${g.asset_id}`} className="tabular font-semibold text-link hover:underline">
        {g.tag_number ?? g.asset_id}
      </Link>
    ),
  },
  { key: "severity", label: "Severity", sortValue: (g) => SEV_RANK[g.severity], render: (g) => <StatusBadge tone={SEV_TONE[g.severity]}>{g.severity}</StatusBadge> },
  {
    key: "status",
    label: "Finding",
    sortable: true,
    sortValue: (g) => (g.status === "gap" ? 0 : 1),
    // Without this the two finding kinds render identically and the clause-scoped
    // detection is invisible: "no evidence at all" reads the same as "evidence exists
    // but nobody verified it", which are different remediations.
    render: (g) =>
      g.status === "unverified_evidence" ? (
        <StatusBadge tone="caution">Unverified evidence</StatusBadge>
      ) : (
        <StatusBadge tone="danger">No evidence</StatusBadge>
      ),
  },
  {
    key: "requires_document_type",
    label: "Requires",
    render: (g) =>
      g.requires_document_type?.length ? (
        <span className="text-caption text-muted">{g.requires_document_type.join(", ").replace(/_/g, " ")}</span>
      ) : (
        "—"
      ),
  },
  { key: "requirement_text", label: "Requirement", render: (g) => truncate(g.requirement_text, "max-w-[320px]") },
  { key: "suggested_remediation", label: "Remediation", render: (g) => truncate(g.suggested_remediation, "max-w-[260px]") },
];

interface ComplianceData {
  gaps: ComplianceGap[];
  dashboard: ComplianceDashboard | null;
}

/** Live-only: gaps are required (getComplianceGaps throws on failure → the page
 *  shows a retry, never a fixture). The dashboard is optional chart enrichment. */
async function fetchCompliance(): Promise<Fetched<ComplianceData>> {
  const [gr, dr] = await Promise.all([getComplianceGaps(), getComplianceDashboard()]);
  return {
    data: { gaps: gr.data?.items ?? [], dashboard: dr.source === "live" ? dr.data : null },
    source: "live",
  };
}

export default function CompliancePage() {
  const state = useFetch(fetchCompliance);
  const loading = state.status === "loading";
  const data = state.status === "live" ? state.data : null;
  const [severity, setSeverity] = useState("all");

  const counts = useMemo<Record<GapSeverity, number>>(() => {
    if (data?.dashboard?.total_gaps) return data.dashboard.total_gaps;
    const acc = { critical: 0, major: 0, minor: 0 };
    for (const g of data?.gaps ?? []) acc[g.severity] += 1;
    return acc;
  }, [data]);

  const byFramework = useMemo(
    () =>
      Object.entries(data?.dashboard?.by_framework ?? {})
        .map(([fw, sev]) => ({ label: fwLabel(fw), value: Object.values(sev ?? {}).reduce((a, b) => a + (b ?? 0), 0) }))
        .sort((a, b) => b.value - a.value),
    [data],
  );

  const slices = useMemo(
    () =>
      [
        { label: "Critical", value: counts.critical, tone: "danger" as const },
        { label: "Major", value: counts.major, tone: "caution" as const },
        { label: "Minor", value: counts.minor, tone: "info" as const },
      ].filter((d) => d.value > 0),
    [counts],
  );

  const rows = useMemo<GapRow[]>(() => {
    const gaps = data?.gaps ?? [];
    return severity === "all" ? gaps : gaps.filter((g) => g.severity === severity);
  }, [data, severity]);

  const lastScan = data?.dashboard?.last_updated;

  return (
    <div data-testid="compliance-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader
        eyebrow="Assure"
        title="Compliance"
        lede="High-recall gap detection: every asset + regulation without a verified procedure is flagged."
        actions={<>
          {lastScan && lastScan !== "realtime" && <span className="text-caption text-muted">Last scan {fmtRelTime(lastScan)}</span>}
        </>}
      />

      {state.status === "error" ? (
        <section data-testid="compliance-error" className="mt-6 rounded-xl border border-line bg-surface p-8 text-center">
          <p className="text-body font-medium text-ink">Couldn&apos;t load compliance posture.</p>
          <p className="mt-1 text-caption text-muted">{state.error.message}</p>
          <button type="button" onClick={state.retry} className="mt-4 inline-flex min-h-11 items-center rounded-lg border border-line bg-surface-2 px-4 text-caption font-medium text-ink transition-colors hover:bg-canvas">
            Retry
          </button>
        </section>
      ) : (
        <>
          {/* KPI strip — count-up via MetricCard; 0 gaps reads as verified, not alarming */}
          <div data-testid="compliance-kpis" className="mt-6 mesh stagger grid-cols-1 sm:grid-cols-3">
            <MetricCard label="Critical" value={counts.critical} sub="Immediate evidence gap" tone={counts.critical > 0 ? "danger" : "verified"} loading={loading} />
            <MetricCard label="Major" value={counts.major} sub="Remediation required" tone={counts.major > 0 ? "caution" : "verified"} loading={loading} />
            <MetricCard label="Minor" value={counts.minor} sub="Track in review cycle" tone={counts.minor > 0 ? "info" : "verified"} loading={loading} />
          </div>

          {/* Charts — zone hidden when the dashboard source is unavailable (partial state) */}
          {(loading || data?.dashboard) && (
            <div data-testid="compliance-charts" className="mt-4 grid gap-4 lg:grid-cols-2">
              <Card className="p-4">
                <h2 className="text-body font-semibold text-ink">Gaps by framework</h2>
                <p className="mt-0.5 text-caption text-muted">Total open gaps per regulation, ranked</p>
                <div className="mt-3">
                  {loading ? <ChartSkeleton height={220} /> : byFramework.length > 0 ? <BarList data={byFramework} height={220} /> : <EmptyState message="No gaps found ✓" />}
                </div>
              </Card>
              <Card className="p-4">
                <h2 className="text-body font-semibold text-ink">Severity mix</h2>
                {/* Clicking a segment filters the register below; clicking the active one clears. */}
                <p className="mt-0.5 text-caption text-muted">Share of open gaps by severity — select a segment to filter</p>
                <div className="mt-3">
                  {loading ? <ChartSkeleton height={220} /> : slices.length > 0 ? <Donut data={slices} centerLabel="total gaps" height={220} activeLabel={severity === "all" ? null : severity} onSliceClick={(d) => setSeverity((cur) => (cur === d.label.toLowerCase() ? "all" : d.label.toLowerCase()))} /> : <EmptyState message="No gaps found ✓" />}
                </div>
              </Card>
            </div>
          )}

          {/* Gap register — sortable severity/framework, paginated past 25 rows */}
          <div className="mt-4">
            <DataTable<GapRow>
              columns={COLUMNS}
              rows={rows}
              keyFn={(g) => `${g.framework}-${g.clause_id}-${g.asset_id}`}
              pageSize={25}
              loading={loading}
              emptyState={
                <div className="rounded-xl border border-line bg-surface px-4 py-6">
                  {(data?.gaps.length ?? 0) > 0 ? (
                    <EmptyState message="No gaps match the current filter." action={{ label: "Clear filter", onClick: () => setSeverity("all") }} />
                  ) : (
                    <EmptyState message="No compliance gaps found." />
                  )}
                </div>
              }
              toolbar={
                <div className="flex w-full flex-wrap items-center justify-between gap-2">
                  <FilterTabs
                    tabs={[
                      { key: "all", label: "All severity" },
                      { key: "critical", label: "Critical", count: counts.critical },
                      { key: "major", label: "Major", count: counts.major },
                      { key: "minor", label: "Minor", count: counts.minor },
                    ]}
                    active={severity}
                    onChange={setSeverity}
                  />
                  <span className="tabular text-caption font-medium text-muted">{rows.length} of {data?.gaps.length ?? 0}</span>
                </div>
              }
            />
          </div>

          {/* Link-card footer — the two compliance workflows (wave-3 pages) */}
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Link href="/compliance/audit-pack" className="block rounded-xl focus-visible:outline-2 focus-visible:outline-accent">
              <Card interactive className="h-full p-5">
                <p className="text-body font-semibold text-ink">Assemble audit pack ›</p>
                <p className="mt-1 text-caption text-muted">Bundle verified evidence for an auditor handover.</p>
              </Card>
            </Link>
            <Link href="/compliance/nonconformance" className="block rounded-xl focus-visible:outline-2 focus-visible:outline-accent">
              <Card interactive className="h-full p-5">
                <p className="text-body font-semibold text-ink">Non-conformance register ›</p>
                <p className="mt-1 text-caption text-muted">Track raised findings through closure.</p>
              </Card>
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
