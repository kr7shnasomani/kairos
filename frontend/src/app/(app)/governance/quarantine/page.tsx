"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { QuarantineItem } from "@/lib/types";
import { getQuarantine } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { Button, DataTable, EmptyState, FilterTabs, PageHeader } from "@/components/ui";
import { useRole, PROMOTE_ROLES } from "@/components/use-role";
import { QueuePills } from "@/components/stat-pills";
import { ItemPanel } from "./_components/item-panel";
import { ActionModals, type ActionMode } from "./_components/actions";
import { buildColumns, type QuarantineRow } from "./_components/columns";

export default function QuarantinePage() {
  const role = useRole();
  const canPromote = PROMOTE_ROLES.includes(role);
  const canResolveDeviation = role === "engineer" || role === "admin";

  const [reload, setReload] = useState(0);
  const state = useFetch(() => getQuarantine(), [reload]);
  const loading = state.status === "loading";

  const [panelId, setPanelId] = useState<string | null>(null);
  const [modal, setModal] = useState<ActionMode | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("pending");

  const [nowMs, setNowMs] = useState(0);
  useEffect(() => {
    const tick = () => setNowMs(Date.now());
    tick();
    const timer = window.setInterval(tick, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const hasData = state.status === "live";
  const items = useMemo<QuarantineItem[]>(() => (hasData ? state.data.items ?? [] : []), [state, hasData]);

  const counts = useMemo(() => {
    const pending = items.filter((i) => i.review_status === "pending");
    const byType: Record<string, number> = {};
    for (const it of pending) byType[it.input_type] = (byType[it.input_type] ?? 0) + 1;
    return {
      pending: pending.length,
      overdue: pending.filter((i) => i.is_overdue).length,
      disputed: items.filter((i) => i.review_status === "disputed").length,
      promoted: items.filter((i) => i.review_status === "promoted").length,
      byType,
    };
  }, [items]);

  // Filter + default order: overdue first, then oldest.
  const rows = useMemo<QuarantineRow[]>(() => {
    return items
      .filter((it) => {
        if (typeFilter !== "all" && it.input_type !== typeFilter) return false;
        if (statusFilter === "pending" && it.review_status !== "pending") return false;
        if (statusFilter === "resolved" && it.review_status === "pending") return false;
        return true;
      })
      .sort((a, b) => Number(b.is_overdue) - Number(a.is_overdue) || Date.parse(a.submitted_at) - Date.parse(b.submitted_at));
  }, [items, typeFilter, statusFilter]);

  const columns = useMemo(() => buildColumns(nowMs), [nowMs]);
  const panelItem = panelId ? items.find((i) => i.item_id === panelId) ?? null : null;

  async function run(mutate: () => Promise<unknown>, success: string, failure: string) {
    if (!panelItem) return;
    setBusy(panelItem.item_id);
    setError(null);
    setNotice(null);
    try {
      await mutate();
      setNotice(success);
      setReload((r) => r + 1);
    } catch {
      setError(failure);
    } finally {
      setModal(null);
      setPanelId(null);
      setBusy(null);
    }
  }

  return (
    <div data-testid="quarantine-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/governance" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Governance
      </Link>

      <PageHeader
        className="mt-4"
        eyebrow="Layer 6 · Quarantine"
        title="Review queue"
        lede="Unverified field inputs awaiting human review. Promotion to the canonical graph is a one-way gate: nothing is auto-promoted, ever."
      />

      <section data-testid="quarantine-summary" className="mt-5">
        <QueuePills
          loading={loading}
          pills={[
            { key: "pending", label: "Pending", value: counts.pending },
            { key: "overdue", label: "Overdue", value: counts.overdue, tone: "danger" },
            { key: "disputed", label: "Disputed", value: counts.disputed },
            { key: "promoted", label: "Promoted", value: counts.promoted },
          ]}
        />
      </section>

      <section data-testid="quarantine-filters" className="mt-4 flex flex-wrap items-center gap-3">
        <FilterTabs
          tabs={[
            { key: "all", label: "All" },
            { key: "pending", label: "Pending", count: counts.pending },
            { key: "resolved", label: "Resolved" },
          ]}
          active={statusFilter}
          onChange={setStatusFilter}
        />
        <FilterTabs
          tabs={[
            { key: "all", label: "All types" },
            { key: "field_observation", label: "Field obs.", count: counts.byType["field_observation"] },
            { key: "voice_note", label: "Voice", count: counts.byType["voice_note"] },
            { key: "elicitation_response", label: "Elicitation", count: counts.byType["elicitation_response"] },
            { key: "offboarding_response", label: "Offboarding", count: counts.byType["offboarding_response"] },
            { key: "deviation_flag", label: "Deviation", count: counts.byType["deviation_flag"] },
          ]}
          active={typeFilter}
          onChange={setTypeFilter}
        />
        {!canPromote && <span className="text-label text-muted">Read-only · {role}</span>}
      </section>

      {error && (
        <p className="mt-3 rounded-lg border border-[color-mix(in_srgb,var(--danger)_35%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_8%,var(--surface))] px-3 py-2 text-caption text-danger">
          {error}
        </p>
      )}
      {notice && (
        <p className="mt-3 rounded-lg border border-[color-mix(in_srgb,var(--verified)_35%,var(--line))] bg-[color-mix(in_srgb,var(--verified)_8%,var(--surface))] px-3 py-2 text-caption text-verified">
          {notice}
        </p>
      )}

      <section data-testid="quarantine-queue" className="mt-4">
        {state.status === "error" ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-line bg-surface px-4 py-10 text-center">
            <p className="text-body text-muted">Could not load the quarantine queue.</p>
            <Button variant="primary" onClick={state.retry}>Retry</Button>
          </div>
        ) : !loading && items.length === 0 ? (
          <EmptyState message="Quarantine is clear ✓" />
        ) : (
          <DataTable<QuarantineRow>
            key={`${statusFilter}:${typeFilter}`}
            columns={columns}
            rows={rows}
            keyFn={(r) => r.item_id}
            pageSize={25}
            loading={loading}
            onRowClick={(r) => setPanelId(r.item_id)}
            emptyState={<EmptyState message="No items match the current filters." />}
          />
        )}
        {hasData && items.length > 0 && (
          <p className="tabular mt-2 text-label text-muted">Queue total {state.data.total}</p>
        )}
      </section>

      {panelItem && (
        <ItemPanel
          item={panelItem}
          nowMs={nowMs}
          canPromote={canPromote}
          canResolveDeviation={canResolveDeviation}
          busy={busy === panelItem.item_id}
          escDisabled={modal !== null}
          onClose={() => setPanelId(null)}
          onAction={setModal}
        />
      )}
      {panelItem && modal && (
        <ActionModals
          item={panelItem}
          mode={modal}
          busy={busy === panelItem.item_id}
          onClose={() => setModal(null)}
          run={run}
        />
      )}
    </div>
  );
}
