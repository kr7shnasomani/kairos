"use client";

// Model-gate dashboard — precision/recall gate on the validation corpus; a
// failed run blocks model promotion. KPI strip (latest run) → pass-mix donut +
// quality trend → paginated run history table. One useFetch drives every zone.
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { TooltipContentProps } from "recharts";
import { CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, ChartContainer, GRID, downsample } from "@/components/charts";
import { ChartTooltip } from "@/components/charts/chart-tooltip";
import { DataTable, EmptyState, MetricCard, PageHeader, StatusBadge, type TableColumn } from "@/components/ui";
import type { Fetched } from "@/lib/api";
import { getModelGateHistory, runModelGate } from "@/lib/api";
import { fmtNum, fmtPct, fmtRelTime } from "@/lib/format";
import { useReducedMotion } from "@/lib/motion";
import type { ModelGateResult } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";
import { useRole, ADMIN_ROLES } from "@/components/use-role";

// There is no fixed F1 bar. The backend fails a run when any entity type or asset class scores below
// the last valid run (workers/model_validation.py). A hard-coded 80% here once labelled a passed
// 72% run as below threshold and coloured it red.
const GATE_RULE = "fails if any entity type regresses";

// ── Demo fixture (backend offline) ────────────────────────────────────────────
/**
 * History rows. Live-but-empty stays empty (EmptyState).
 *
 * There is no fixture fallback: this page previously substituted FIXTURE_HISTORY — invented
 * runs with made-up F1 values (0.825, 0.775) — when the fetch failed. On the one page whose
 * whole purpose is to show *measured* model evidence, that is the most damaging place in the
 * app to fabricate. `getModelGateHistory` now throws and useFetch renders error+retry.
 */
async function fetchHistory(): Promise<Fetched<ModelGateResult[]>> {
  const res = await getModelGateHistory();
  return { data: res.data?.history ?? [], source: "live" };
}

/** ModelGateResult re-mapped so it satisfies DataTable's Record constraint. */
type GateRow = Pick<ModelGateResult, keyof ModelGateResult>;

/** Ratio → 0–100 chart value; bad input → null (recharts draws a gap, never NaN). */
const pct100 = (v: number | null | undefined) => (typeof v === "number" && Number.isFinite(v) ? v * 100 : null);

const TREND_SERIES = [
  { key: "Precision", color: "var(--accent)" },
  { key: "Recall", color: "var(--info)" },
  { key: "F1", color: "var(--muted)" },
] as const;

/** Trend tooltip — all three series plus that run's corpus size in the label. */
function TrendTip(props: Partial<TooltipContentProps<number | string, string>>) {
  const row = props.payload?.[0]?.payload as { day?: string; corpus_size?: number } | undefined;
  const label = row?.day ? `${row.day} · corpus ${fmtNum(row.corpus_size)}` : props.label;
  return <ChartTooltip {...props} label={label} valueFormat={(v) => `${fmtNum(v, 1)}%`} />;
}

const COLUMNS: TableColumn<GateRow>[] = [
  { key: "run_at", label: "Run", sortValue: (r) => Date.parse(r.run_at) || 0, render: (r) => <span className="tabular text-muted">{fmtRelTime(r.run_at)}</span> },
  { key: "precision", label: "Precision", className: "text-right", sortValue: (r) => r.precision ?? -1, render: (r) => <span className="tabular">{fmtPct(r.precision)}</span> },
  { key: "recall", label: "Recall", className: "text-right", sortValue: (r) => r.recall ?? -1, render: (r) => <span className="tabular">{fmtPct(r.recall)}</span> },
  { key: "f1", label: "F1", className: "text-right", sortValue: (r) => r.f1 ?? -1, render: (r) => (
    <span className="tabular font-semibold" style={{ color: r.passed ? "var(--verified)" : "var(--danger)" }}>{fmtPct(r.f1)}</span>
  ) },
  { key: "corpus_size", label: "Corpus", className: "text-right", sortValue: (r) => r.corpus_size ?? -1, render: (r) => <span className="tabular text-muted">{fmtNum(r.corpus_size)}</span> },
  { key: "passed", label: "Gate", render: (r) => <StatusBadge tone={r.passed ? "verified" : "danger"}>{r.passed ? "passed" : "failed"}</StatusBadge> },
];

export default function ModelGatePage() {
  // reloadKey lets a completed run refresh every zone (KPIs, charts, table) via useFetch's deps.
  const [reloadKey, setReloadKey] = useState(0);
  const state = useFetch(fetchHistory, [reloadKey]);
  const loading = state.status === "loading";
  const history = state.status === "live" ? state.data : null;
  const reduced = useReducedMotion();
  const role = useRole();
  const isAdmin = ADMIN_ROLES.includes(role);
  const [running, setRunning] = useState(false);
  const [queued, setQueued] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Stop polling on unmount.
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // Newest-first — the table's default order (run_at desc); [0] is the latest run.
  const rows = useMemo(
    () => (history ? [...history].sort((a, b) => (Date.parse(b.run_at) || 0) - (Date.parse(a.run_at) || 0)) : []),
    [history],
  );
  const latest = rows[0] ?? null;
  const passedCount = rows.filter((r) => r.passed).length;
  const passRate = rows.length > 0 ? passedCount / rows.length : null;

  // Oldest-first for the trend axis; capped at 500 points.
  const trend = useMemo(
    () => downsample([...rows].reverse().map((r) => ({
      day: new Date(r.run_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      Precision: pct100(r.precision), Recall: pct100(r.recall), F1: pct100(r.f1), corpus_size: r.corpus_size,
    }))),
    [rows],
  );

  async function handleRun() {
    setRunning(true);
    setRunError(null);
    // The gate evaluates the NER model over the whole validation corpus (a NIM call per
    // item) — it runs ~2-3 min on the Celery queue. The POST only *enqueues* it, so poll
    // the history until a newer run appears, then refresh every zone.
    const baselineTop = latest?.run_at ?? "";
    try {
      await runModelGate();
      setQueued(true);
      if (pollRef.current) clearInterval(pollRef.current);
      let attempts = 0;
      pollRef.current = setInterval(async () => {
        attempts += 1;
        try {
          const res = await getModelGateHistory();
          const newTop = res.data?.history[0]?.run_at ?? "";
          if (newTop && newTop > baselineTop) {
            if (pollRef.current) clearInterval(pollRef.current);
            setQueued(false);
            setReloadKey((k) => k + 1); // refresh KPIs, charts, table
            return;
          }
        } catch { /* transient — keep polling */ }
        if (attempts >= 15) { // ~5 min ceiling
          if (pollRef.current) clearInterval(pollRef.current);
          setQueued(false);
        }
      }, 20_000);
    } catch (e) {
      // Distinguish a permission failure (admin-only endpoint) and other server
      // errors from an actual offline backend — postJson encodes the status as
      // "… → HTTP <code>"; a network/timeout failure has no HTTP code.
      const msg = e instanceof Error ? e.message : "";
      const code = msg.match(/HTTP (\d+)/)?.[1];
      if (code === "403") {
        setRunError("You don't have permission to run the gate — this action is admin-only.");
      } else if (code) {
        setRunError(`Couldn't trigger the run — the server returned ${code}. Try again.`);
      } else {
        setRunError("Couldn't reach the backend — check your connection and retry.");
      }
    } finally {
      setRunning(false);
    }
  }

  return (
    <div data-testid="model-gate-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/governance" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Governance
      </Link>

      <PageHeader
        className="mt-4"
        eyebrow="Layer 12 · Model Gate"
        title="Model Gate"
        lede="Precision / recall gate on the validation corpus. A failed run blocks model promotion. Runs are triggered manually or by the nightly Temporal workflow."
        actions={
          // Running the gate is admin-only on the backend (403 otherwise), so only
          // admins see the trigger. Everyone else views history read-only.
          isAdmin ? (
            <button
              onClick={handleRun}
              disabled={running || queued}
              className="inline-flex min-h-11 items-center rounded-lg bg-accent px-3.5 text-body font-semibold text-on-accent transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {running ? "Triggering…" : queued ? "Running…" : "Run gate now"}
            </button>
          ) : undefined
        }
      />

      {queued && (
        <p className="mt-2 text-caption text-accent">
          Gate run queued — it evaluates the NER model over the validation corpus and takes ~2–3 minutes. This page refreshes automatically when the run lands.
        </p>
      )}
      {runError && <p className="mt-2 text-caption text-danger">{runError}</p>}

      {state.status === "error" ? (
        <section data-testid="model-gate-error" className="mt-6 rounded-xl border border-line bg-surface p-8 text-center">
          <p className="text-body font-medium text-ink">Couldn&apos;t load gate history.</p>
          <p className="mt-1 text-caption text-muted">{state.error.message}</p>
          <button type="button" onClick={state.retry} className="mt-4 inline-flex min-h-11 items-center rounded-lg border border-line bg-surface-2 px-4 text-caption font-medium text-ink transition-colors hover:bg-canvas">
            Retry
          </button>
        </section>
      ) : (
        <>
          {/* KPI strip — latest run quality + pass rate across history */}
          <div data-testid="model-gate-summary" className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Precision" value={fmtPct(latest?.precision)} sub="latest run" tone="accent" loading={loading} />
            <MetricCard label="Recall" value={fmtPct(latest?.recall)} sub="latest run" tone="info" loading={loading} />
            <MetricCard label="F1" value={fmtPct(latest?.f1)} sub={GATE_RULE} tone="neutral" loading={loading} />
            <MetricCard label="Pass rate" value={fmtPct(passRate)} sub={`${passedCount} of ${rows.length} runs`} tone={!latest ? "neutral" : latest.passed ? "verified" : "danger"} loading={loading} />
          </div>

          {/* Pass mix + quality trend — asymmetric 2fr/3fr split */}
          <div data-testid="model-gate-layout" className="mt-5 grid items-start gap-6 lg:grid-cols-[2fr_3fr]">
            <ChartContainer title="Pass mix" sub="All recorded runs" height={240} collapsible loading={loading} empty={rows.length === 0 ? "No gate runs yet." : undefined}>
              <PieChart>
                <Pie data={[{ name: "Passed", value: passedCount }, { name: "Failed", value: rows.length - passedCount }]} dataKey="value" nameKey="name" cy="45%" innerRadius={60} outerRadius={90} paddingAngle={2} stroke="none" isAnimationActive={!reduced}>
                  <Cell fill="var(--verified)" />
                  <Cell fill="var(--danger)" />
                </Pie>
                <text x="50%" y="45%" dy={-4} textAnchor="middle" dominantBaseline="middle" className="tabular" style={{ fill: "var(--ink)", fontSize: 22, fontWeight: 600 }}>{rows.length}</text>
                <text x="50%" y="45%" dy={16} textAnchor="middle" dominantBaseline="middle" style={{ fill: "var(--muted)", fontSize: 11 }}>runs</text>
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: "var(--muted)" }} />
                <Tooltip content={<ChartTooltip />} />
              </PieChart>
            </ChartContainer>
            <ChartContainer title="Quality trend" sub="Precision / recall / F1 per run" height={240} collapsible loading={loading} empty={rows.length === 0 ? "No gate runs yet." : undefined}>
              <LineChart data={trend} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="day" {...AXIS} minTickGap={24} />
                <YAxis {...AXIS} width={44} domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} />
                <Tooltip content={<TrendTip />} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: "var(--muted)" }} />
                {TREND_SERIES.map((s) => (
                  <Line key={s.key} type="monotone" dataKey={s.key} stroke={s.color} strokeWidth={2} dot={trend.length < 3} isAnimationActive={!reduced} />
                ))}
              </LineChart>
            </ChartContainer>
          </div>

          {/* Full run history */}
          <section data-testid="model-gate-history" className="mt-5">
            <h2 className="mb-3 text-label font-bold uppercase tracking-[0.1em] text-muted">Run history</h2>
            <DataTable<GateRow> columns={COLUMNS} rows={rows} keyFn={(r) => r.run_id} pageSize={25} loading={loading} emptyState={<EmptyState message="No gate runs yet." />} />
          </section>
        </>
      )}
    </div>
  );
}
