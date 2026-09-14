"use client";

// Push-volume gate — EEMUA 191 ceiling on briefs per operator per hour, measured over a window.
// Reporting only: it informs the phase decision, it never blocks delivery.
import { useState } from "react";
import { Button, DataTable, EmptyState, KpiCard, PageHeader, StatusBadge, type TableColumn } from "@/components/ui";
import { getPushVolumeGate, type PushVolumeGate } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";

type Breach = PushVolumeGate["breaches"][number] & Record<string, unknown>;

const WINDOWS = [7, 30, 90] as const;

const COLUMNS: TableColumn<Breach>[] = [
  { key: "recipient_user_id", label: "Operator", render: (r) => <span className="tabular text-caption font-medium text-ink">{r.recipient_user_id}</span> },
  { key: "hour", label: "Hour (UTC)", sortable: true, render: (r) => <span className="tabular text-caption">{r.hour.replace("T", " ")}:00</span> },
  { key: "count", label: "Briefs", align: "right", sortable: true, render: (r) => <span className="tabular font-semibold text-danger">{r.count}</span> },
];

export default function PushVolumeGatePage() {
  const [days, setDays] = useState<number>(30);
  const state = useFetch(() => getPushVolumeGate(days), [days]);
  const gate = state.status === "live" ? state.data : null;
  const loading = state.status === "loading";

  return (
    <div data-testid="push-volume-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader
        eyebrow="EEMUA 191 · Alert discipline"
        title="Push-volume gate"
        lede="Governed proactive mode stays the default only while briefs per operator stay within the hourly ceiling. This report informs that decision; it never blocks delivery."
        actions={
          <label className="flex items-center gap-2 text-caption">
            <span className="font-semibold text-ink">Window</span>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="h-9 rounded-lg border border-line bg-surface px-2.5 text-body">
              {WINDOWS.map((d) => <option key={d} value={d}>{d} days</option>)}
            </select>
          </label>
        }
      />

      {state.status === "error" ? (
        <section className="mt-6 rounded-xl border border-line bg-surface p-8 text-center">
          <p className="text-body font-medium text-ink">Couldn&apos;t load the push-volume gate.</p>
          <p className="mt-1 text-caption text-muted">{state.error.message}</p>
          <Button className="mt-4" onClick={state.retry}>Retry</Button>
        </section>
      ) : (
        <>
          {gate && (
            <div className="mt-5 flex flex-wrap items-center gap-2 text-caption text-muted">
              <StatusBadge tone={gate.within_eemua_norms ? "verified" : "danger"}>
                {gate.within_eemua_norms ? "Within EEMUA 191 norms" : "Ceiling breached"}
              </StatusBadge>
              <span>Phase {gate.current_phase} · advisory only</span>
            </div>
          )}
          <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
            <KpiCard label="Briefs delivered" value={gate?.briefs_delivered} sub={gate ? `Last ${gate.window_days} days` : undefined} loading={loading} />
            <KpiCard label="Peak per operator" value={gate ? `${gate.peak_per_operator_per_hour}/h` : null} sub={gate ? `Ceiling ${gate.ceiling_per_operator_per_hour}/h` : undefined} tone={gate && gate.peak_per_operator_per_hour > gate.ceiling_per_operator_per_hour ? "danger" : "neutral"} loading={loading} />
            <KpiCard label="Breaching hours" value={gate?.breach_count} tone={gate?.breach_count ? "danger" : "neutral"} loading={loading} />
            <KpiCard label="Ceiling" value={gate ? `${gate.ceiling_per_operator_per_hour}/h` : null} sub="PTW briefs exempt" loading={loading} />
          </div>
          <div className="mt-6">
            <h2 className="mb-2 text-sm font-semibold text-ink">Operator-hours over the ceiling</h2>
            <DataTable
              columns={COLUMNS}
              rows={(gate?.breaches ?? []) as Breach[]}
              keyFn={(r) => `${r.recipient_user_id}-${r.hour}`}
              loading={loading}
              emptyState={
                <EmptyState
                  message={gate?.briefs_delivered
                    ? `No operator exceeded ${gate.ceiling_per_operator_per_hour} briefs in any hour of the last ${gate.window_days} days.`
                    : `No briefs delivered in the last ${days} days.`}
                  action={{ label: "Open briefs", href: "/briefs" }}
                />
              }
            />
          </div>
        </>
      )}
    </div>
  );
}
