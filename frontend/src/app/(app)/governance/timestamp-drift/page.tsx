"use client";

// Timestamp drift — clock skew between source systems reporting the SAME compound event.
// Report-only while TIMESTAMP_DRIFT_ENFORCE is off: nothing here opens a conflict.
import { Button, DataTable, EmptyState, KpiCard, PageHeader, StatusBadge, type TableColumn } from "@/components/ui";
import { getTimestampDrift, type DriftItem } from "@/lib/api";
import { fmtRelTime } from "@/lib/format";
import { useFetch } from "@/lib/use-fetch";

type Row = DriftItem & Record<string, unknown>;

const COLUMNS: TableColumn<Row>[] = [
  { key: "compound_event_id", label: "Compound event", render: (r) => <span className="tabular font-semibold text-ink">{r.compound_event_id}</span> },
  { key: "sources", label: "Source systems", render: (r) => <span className="text-caption">{r.sources.join(" · ")}</span> },
  { key: "drift_minutes", label: "Drift", align: "right", sortable: true, render: (r) => <span className="tabular font-semibold text-caution">{r.drift_minutes} min</span> },
  {
    key: "canonical_timestamp", label: "Canonical time",
    render: (r) => r.canonical_timestamp
      ? <span className="tabular text-caption" title={r.canonical_timestamp}>{fmtRelTime(r.canonical_timestamp)}<span className="text-muted"> · {r.canonical_source}</span></span>
      : <span className="text-muted">—</span>,
  },
  { key: "action", label: "Action", render: (r) => <StatusBadge tone={r.action === "conflict_opened" ? "caution" : "neutral"} dot={false}>{(r.action ?? "reported_only").replace(/_/g, " ")}</StatusBadge> },
];

export default function TimestampDriftPage() {
  const state = useFetch(getTimestampDrift);
  const report = state.status === "live" ? state.data : null;
  const loading = state.status === "loading";

  return (
    <div data-testid="timestamp-drift-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader
        eyebrow="Layer 4 · Temporal alignment"
        title="Timestamp drift"
        lede="Clock disagreement between systems that recorded the same physical event. Occurred-versus-ingested gaps are history, not drift, and are never counted."
      />

      {state.status === "error" ? (
        <section className="mt-6 rounded-xl border border-line bg-surface p-8 text-center">
          <p className="text-body font-medium text-ink">Couldn&apos;t load the drift report.</p>
          <p className="mt-1 text-caption text-muted">{state.error.message}</p>
          <Button className="mt-4" onClick={state.retry}>Retry</Button>
        </section>
      ) : (
        <>
          <div className="mt-6 grid grid-cols-2 gap-2 lg:grid-cols-4">
            <KpiCard label="Compound events checked" value={report?.compound_events_checked} loading={loading} />
            <KpiCard label="Drift detected" value={report?.drift_detected_count} tone={report?.drift_detected_count ? "caution" : "neutral"} loading={loading} />
            <KpiCard label="Tolerance" value={report ? `${report.tolerance_minutes} min` : null} loading={loading} />
            <KpiCard label="Enforcement" value={report ? (report.enforcement === "enforced" ? "Enforced" : "Advisory") : null} sub={report?.enforcement === "enforced" ? "Opens administrative conflicts" : "Reported only"} loading={loading} />
          </div>
          <div className="mt-6">
            <DataTable
              columns={COLUMNS}
              rows={(report?.items ?? []) as Row[]}
              keyFn={(r) => r.compound_event_id}
              loading={loading}
              pageSize={25}
              emptyState={
                <EmptyState
                  message={report?.compound_events_checked
                    ? `No drift beyond ${report.tolerance_minutes} minutes across ${report.compound_events_checked} compound events.`
                    : "No compound events recorded yet — drift needs two systems reporting the same event."}
                  action={{ label: "Open events", href: "/events" }}
                />
              }
            />
          </div>
        </>
      )}
    </div>
  );
}
