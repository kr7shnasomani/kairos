"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getConflicts, resolveConflict } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { Button, DataTable, EmptyState, FilterTabs, PageHeader } from "@/components/ui";
import { StatPills } from "@/components/stat-pills";
import { buildColumns, type ConflictRow } from "./_components/columns";

import { Icon } from "@/components/icon";
const TEST_PREFIXES = ["ASSET-TEST-", "ASSET-EV-", "ASSET-DEDUP-"];
const isTestData = (c: ConflictRow) => TEST_PREFIXES.some((p) => c.asset_id?.startsWith(p));


export default function ConflictsPage() {
  // Spec §5: params unchanged — same zero-arg getConflicts() call as before.
  const state = useFetch(() => getConflicts(), []);
  const loading = state.status === "loading";
  const hasData = state.status === "live";

  const [resolved, setResolved] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("open");
  const [trackFilter, setTrackFilter] = useState("all");
  const [showTestData, setShowTestData] = useState(false);
  const [nowMs, setNowMs] = useState(0);

  useEffect(() => {
    const tick = () => setNowMs(Date.now());
    tick();
    const timer = window.setInterval(tick, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  // Fetched items with optimistic resolve overrides applied.
  const items = useMemo<ConflictRow[]>(() => {
    const fetched = hasData ? state.data.items ?? [] : [];
    return fetched.map((c) => (resolved.has(c.conflict_id) ? { ...c, status: "resolved" as const } : c));
  }, [state, hasData, resolved]);

  async function resolve(c: ConflictRow) {
    setBusy(c.conflict_id);
    setError(null);
    setResolved((s) => new Set(s).add(c.conflict_id));
    try {
      await resolveConflict(c.conflict_id, { decision: "accept_higher_authority" });
    } catch {
      setResolved((s) => { const next = new Set(s); next.delete(c.conflict_id); return next; });
      setError(`Could not resolve ${c.conflict_id} — backend offline or rejected.`);
    } finally {
      setBusy(null);
    }
  }

  const scoped = useMemo(() => items.filter((c) => showTestData || !isTestData(c)), [items, showTestData]);
  const counts = useMemo(() => ({
    open: scoped.filter((c) => c.status === "open").length,
    pendingMoc: scoped.filter((c) => c.status === "pending_moc").length,
    resolved: scoped.filter((c) => c.status === "resolved").length,
    overdue: scoped.filter((c) => c.status !== "resolved" && c.is_overdue).length,
  }), [scoped]);

  const rows = useMemo(() => scoped.filter((c) => {
    if (statusFilter === "open" && c.status === "resolved") return false;
    if (statusFilter === "resolved" && c.status !== "resolved") return false;
    if (trackFilter !== "all" && c.track !== trackFilter) return false;
    return true;
  }), [scoped, statusFilter, trackFilter]);

  const columns = useMemo(() => buildColumns(nowMs, busy, resolve), [nowMs, busy]);
  const hasFilters = statusFilter !== "all" || trackFilter !== "all";

  return (
    <div data-testid="conflicts-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/governance" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <Icon name="caret-left" size={15} />
        Governance
      </Link>

      <PageHeader
        className="mt-4"
        title="Conflicts"
        lede="Contradictions between sources, split by track. Administrative conflicts resolve here; engineering conflicts are safety-critical and route through Management of Change."
      />

      <section data-testid="conflicts-summary" className="mt-5">
        <StatPills
          loading={loading}
          pills={[
            { key: "open", label: "Open", value: counts.open },
            { key: "pending_moc", label: "Pending MoC", value: counts.pendingMoc },
            { key: "resolved", label: "Resolved", value: counts.resolved },
            { key: "overdue", label: "SLA overdue", value: counts.overdue, tone: "danger" },
          ]}
        />
      </section>

      <section data-testid="conflicts-filters" className="mt-4 flex flex-wrap items-center gap-3">
        <FilterTabs
          tabs={[
            { key: "all", label: "All" },
            { key: "open", label: "Open", count: counts.open + counts.pendingMoc },
            { key: "resolved", label: "Resolved" },
          ]}
          active={statusFilter}
          onChange={setStatusFilter}
        />
        <FilterTabs
          tabs={[
            { key: "all", label: "All tracks" },
            { key: "administrative", label: "Administrative" },
            { key: "engineering", label: "Engineering" },
          ]}
          active={trackFilter}
          onChange={setTrackFilter}
        />
        <label className="ml-auto flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-label text-muted hover:bg-surface-2">
          <input type="checkbox" checked={showTestData} onChange={(e) => setShowTestData(e.target.checked)} className="size-4 rounded accent-accent" />
          Show test data
        </label>
      </section>

      {error && (
        <p className="mt-3 rounded-lg border border-[color-mix(in_srgb,var(--danger)_35%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_8%,var(--surface))] px-3 py-2 text-caption text-danger">
          {error}
        </p>
      )}

      <section data-testid="conflicts-queue" className="mt-4">
        {state.status === "error" ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-line bg-surface px-4 py-10 text-center">
            <p className="text-body text-muted">Could not load the conflict queue.</p>
            <Button variant="primary" onClick={state.retry}>Retry</Button>
          </div>
        ) : (
          <DataTable<ConflictRow>
            key={`${statusFilter}:${trackFilter}:${showTestData}`}
            columns={columns}
            rows={rows}
            keyFn={(r) => r.conflict_id}
            pageSize={25}
            loading={loading}
            emptyState={<EmptyState message={hasFilters && scoped.length > 0 ? "No conflicts match the current filters." : "No conflicts — knowledge is consistent ✓"} />}
          />
        )}
        {hasData && <p className="tabular mt-2 text-label text-muted">{rows.length} of {scoped.length} conflicts</p>}
      </section>
    </div>
  );
}
