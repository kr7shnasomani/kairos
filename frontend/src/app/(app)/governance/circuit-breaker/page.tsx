"use client";

import Link from "next/link";
import { useMemo } from "react";
import type { CircuitBreakerEntry } from "@/lib/types";
import { getCircuitBreaker } from "@/lib/api";
import { DataTable, EmptyState, MetricCard, PageHeader, StatusBadge, type TableColumn } from "@/components/ui";
import { Card } from "@/components/ui-card";
import { BarList } from "@/components/charts/bar-list";
import { ChartSkeleton } from "@/components/skeleton";
import { useFetch } from "@/lib/use-fetch";
import { fmtNum } from "@/lib/format";
import { triggerLabel } from "@/lib/utils";


import { Icon } from "@/components/icon";
// DataTable needs an index signature; Pick over the interface provides one.
type BreakerRow = Pick<CircuitBreakerEntry, keyof CircuitBreakerEntry>;

function zTone(e: BreakerRow): "danger" | "caution" | "verified" {
  return e.halted ? "danger" : (e.z_score ?? 0) >= 2 ? "caution" : "verified";
}

const COLUMNS: TableColumn<BreakerRow>[] = [
  { key: "asset_class", label: "Asset class", sortable: true, render: (r) => <span className="font-semibold text-ink">{r.asset_class}</span> },
  { key: "halted", label: "Status", sortable: true, sortValue: (r) => (r.halted ? 1 : 0), render: (r) => <StatusBadge tone={r.halted ? "danger" : "verified"}>{r.halted ? "halted" : "ok"}</StatusBadge> },
  { key: "z_score", label: "z-score", sortable: true, sortValue: (r) => r.z_score ?? 0, render: (r) => <span className="tabular" style={{ color: `var(--${zTone(r)})` }}>{fmtNum(r.z_score, 1)}σ</span> },
  { key: "override_count_7d", label: "Overrides 7d", sortable: true, sortValue: (r) => r.override_count_7d ?? 0, render: (r) => <span className="tabular">{fmtNum(r.override_count_7d)}</span> },
  { key: "reason", label: "Reason", render: (r) => <span className="block max-w-[220px] truncate text-muted" title={r.reason ?? undefined}>{r.reason ? triggerLabel(r.reason) : "—"}</span> },
];

export default function CircuitBreakerPage() {
  const state = useFetch(getCircuitBreaker);
  const loading = state.status === "loading";
  // Live-only: no fixture fallback. This used to be `state.data ?? FIXTURE`, which invented
  // halted breakers for Valve and Separator — fabricated governance state on a page whose
  // entire purpose is reporting whether extraction has actually been halted.
  const cb = state.status === "live" ? state.data : null;
  const states = useMemo(() => cb?.states ?? [], [cb]);
  const halted = states.filter((e) => e.halted);
  const maxZ = states.length > 0 ? Math.max(...states.map((e) => e.z_score ?? 0)) : null;
  const overrides = states.reduce((n, e) => n + (e.override_count_7d ?? 0), 0);
  const bars = useMemo(
    () =>
      [...states]
        .sort((a, b) => (b.z_score ?? 0) - (a.z_score ?? 0))
        .map((e) => ({ label: e.asset_class, value: e.z_score ?? 0, tone: zTone(e) })),
    [states],
  );

  return (
    <div data-testid="circuit-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/governance" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <Icon name="caret-left" size={15} />
        Governance
      </Link>

      <PageHeader className="mt-4" eyebrow="Governance" title="Circuit Breaker" lede="Statistical process control gates that halt ingestion for an asset class when z-score anomalies exceed threshold. Halted classes require admin override or human-verified resolution." />
      {state.status === "error" && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-[color-mix(in_srgb,var(--danger)_30%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_5%,var(--surface))] p-4 text-body text-ink">
          Couldn&rsquo;t load circuit-breaker state.
          <button onClick={state.retry} className="font-semibold text-accent underline hover:no-underline">Retry</button>
        </div>
      )}

      <div data-testid="circuit-summary" className="mt-5 mesh stagger sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Halted" value={cb ? halted.length : null} tone={halted.length > 0 ? "danger" : "verified"} sub={halted.length === 0 && cb ? "all paths open" : undefined} loading={loading} />
        <MetricCard label="Watched classes" value={cb ? states.length : null} loading={loading} />
        <MetricCard label="Max z-score" value={cb && maxZ !== null ? `${fmtNum(maxZ, 1)}σ` : null} tone={maxZ !== null && maxZ >= 2 ? "caution" : "neutral"} loading={loading} />
        <MetricCard label="Overrides 7d" value={cb ? overrides : null} tone={overrides > 0 ? "caution" : "neutral"} loading={loading} />
      </div>

      <Card className="mt-4 p-4 shadow-sm">
        <h2 className="text-body font-semibold text-ink">z-score by asset class</h2>
        <p className="mt-0.5 text-caption text-muted">Deviation from baseline, ranked. Halt threshold ≥ 2.0σ; halted classes in red.</p>
        <div className="mt-3">
          {loading
            ? <ChartSkeleton height={200} />
            : bars.length > 0
            ? <BarList data={bars} height={Math.max(140, bars.length * 36)} valueFormat={(v) => `${fmtNum(v, 1)}σ`} />
            : <EmptyState message="All breakers closed ✓ — no asset class under SPC watch." />}
        </div>
      </Card>

      <div data-testid="circuit-layout" className="mt-4 grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div data-testid="circuit-monitor" className="min-w-0">
          <DataTable
            columns={COLUMNS}
            rows={states as BreakerRow[]}
            keyFn={(r) => String(r.asset_class)}
            loading={loading}
            emptyState={<EmptyState message="All breakers closed ✓" />}
          />
        </div>

        <aside data-testid="circuit-context" className="rounded-xl border border-line bg-surface p-4 text-caption text-muted shadow-sm lg:sticky lg:top-6">
          <p className="font-semibold text-ink">What triggers a halt?</p>
          <p className="mt-2 leading-relaxed">
            A z-score ≥ 2.0σ on ingested values for an asset class. Overrides by field workers increment the counter; ≥ 5 overrides/7d
            auto-escalates to admin review. Only admins can manually clear a halt.
          </p>
          <div className="mt-4 border-t border-line pt-3">
            <p className="text-micro font-semibold uppercase tracking-[0.1em] text-muted">Current posture</p>
            <p className="mt-1.5 font-medium text-ink">
              {halted.length === 0 ? "All ingestion paths are open." : `${halted.length} asset ${halted.length === 1 ? "class requires" : "classes require"} review.`}
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
