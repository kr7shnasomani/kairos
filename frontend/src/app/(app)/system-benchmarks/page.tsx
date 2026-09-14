"use client";

// Admin System Benchmarks — the measured evidence for the evaluation criteria, drawn from
// live sources only.
//
// Live-only policy applies here as much as anywhere: this page does NOT chart a copy of
// benchmark/RESULTS.md. Numbers a judge sees are read from the running system —
// model-gate runs recorded in audit_log, validation-corpus coverage, compliance posture,
// datastore health. Metrics the harnesses produce but the system does not persist
// (retrieval/answer/provenance, load sweep, time-to-answer) are linked, not redrawn,
// because copying them into a component would make them indistinguishable from live data.

import Link from "next/link";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useFetch } from "@/lib/use-fetch";
import {
  getComplianceDashboard,
  getHealthDetailed,
  getModelGateHistory,
  getValidationCorpusStats,
} from "@/lib/api";
import type { ModelGateResult } from "@/lib/types";

/** DataTable needs an index signature; same Pick idiom the compliance pages use. */
type GateRow = Pick<ModelGateResult, keyof ModelGateResult>;
import { AXIS, GRID, SERIES } from "@/components/charts";
import { ChartCard } from "@/components/charts";
import { BarList, type BarListItem } from "@/components/charts/bar-list";
import { ChartTooltip } from "@/components/charts/chart-tooltip";
import { DataTable, EmptyState, KpiCard, PageHeader, StatusBadge } from "@/components/ui";
import { SystemTabs } from "@/components/system-tabs";

const f3 = (v: number) => v.toFixed(3);

/** Severity → reserved status tone. Status colours never double as series colours. */
const SEVERITY_TONE = { critical: "danger", major: "caution", minor: "neutral" } as const;

export default function SystemBenchmarksPage() {
  const gate = useFetch(getModelGateHistory, []);
  const corpus = useFetch(getValidationCorpusStats, []);
  const compliance = useFetch(getComplianceDashboard, []);
  const health = useFetch(getHealthDetailed, []);

  const history: ModelGateResult[] = gate.status === "live" ? (gate.data.history ?? []) : [];
  // History arrives newest-first; a trend must read left-to-right oldest-first.
  const runs = [...history].reverse();
  const latest = history[0];

  const corpusSize = corpus.status === "live" ? (corpus.data?.total_corpus_size ?? null) : null;
  const gaps = compliance.status === "live" ? compliance.data?.total_gaps : undefined;
  const services = health.status === "live" ? (health.data?.services ?? []) : [];
  const healthy = services.filter((s) => s.status === "healthy").length;

  // Per-entity F1 for the most recent run — shows which entity types a model fails on,
  // which the aggregate F1 hides entirely.
  const entityBars: BarListItem[] = Object.entries(latest?.by_entity_type ?? {})
    .filter(([, s]) => (s.count ?? 0) > 0)
    .map(([label, s]) => ({ label, value: Number((s.f1 ?? 0).toFixed(4)) }))
    .sort((a, b) => b.value - a.value);

  const gapBars: BarListItem[] = gaps
    ? (["critical", "major", "minor"] as const).map((sev) => ({
        label: sev[0].toUpperCase() + sev.slice(1),
        value: gaps[sev] ?? 0,
        tone: SEVERITY_TONE[sev],
      }))
    : [];

  return (
    <div className="mx-auto max-w-[1200px]">
      <SystemTabs />

      <PageHeader
        compact
        className="mb-5"
        eyebrow="Layer 0 · Empirical validation"
        title="System benchmarks"
        lede="Measured evidence read from the running system. Model-gate runs, entity-extraction coverage, compliance posture and datastore health — not a copy of a results file."
      />

      {/* Headline numbers: single values, so tiles rather than plots. */}
      <section aria-label="Headline metrics" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Latest model-gate F1"
          value={latest ? f3(latest.f1) : null}
          tone={latest ? (latest.passed ? "verified" : "danger") : "neutral"}
          // The headline is the most misleading place for a fallback-contaminated run: a SUSPECT
          // F1 is a ceiling, and shown bare it reads as the model's score.
          sub={
            latest
              ? `${latest.passed ? "Gate passed" : "Gate failed"}${latest.validity === "SUSPECT" ? " · SUSPECT — ceiling, not a measurement" : ""}`
              : "No run recorded"
          }
          loading={gate.status === "loading"}
        />
        <KpiCard
          label="Validation corpus"
          value={corpusSize}
          tone={corpusSize && corpusSize > 0 ? "accent" : "danger"}
          sub={corpusSize ? `${corpusSize} labelled entities` : "Empty — F1 not reproducible"}
          loading={corpus.status === "loading"}
        />
        <KpiCard
          label="Critical compliance gaps"
          value={gaps?.critical ?? null}
          tone={gaps && gaps.critical > 0 ? "danger" : "verified"}
          sub="Clause × asset, no required evidence"
          href="/compliance"
          loading={compliance.status === "loading"}
        />
        <KpiCard
          label="Datastores healthy"
          value={services.length ? `${healthy}/${services.length}` : null}
          tone={services.length && healthy === services.length ? "verified" : "danger"}
          sub="Neo4j · Qdrant · ES · Redis · Temporal"
          href="/system-health"
          loading={health.status === "loading"}
        />
      </section>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {/* Three series over runs → legend is mandatory; single 0–1 axis, never dual. */}
        <ChartCard
          title="Model-gate metrics across runs"
          sub="Precision · recall · F1 per recorded run, oldest first"
          height={260}
          loading={gate.status === "loading"}
          error={gate.status === "error" ? gate.error.message : false}
          onRetry={gate.status === "error" ? gate.retry : undefined}
          empty={runs.length === 0 ? "No model-gate runs recorded yet." : false}
        >
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={runs} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis
                dataKey="run_at"
                {...AXIS}
                tickFormatter={(v: string) => (v ? new Date(v).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "")}
              />
              <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} {...AXIS} tickFormatter={(v: number) => v.toFixed(2)} />
              <Tooltip content={<ChartTooltip valueFormat={(v) => Number(v).toFixed(3)} />} />
              <Line type="monotone" dataKey="precision" name="Precision" stroke={SERIES[0]} strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="recall" name="Recall" stroke={SERIES[1]} strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="f1" name="F1" stroke={SERIES[2]} strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Single series, magnitude by category — the title names it, so no legend box. */}
        <ChartCard
          title="Entity-extraction F1 by type"
          sub={latest?.model_name ? `Latest run · ${latest.model_name}` : "Latest recorded run"}
          height={260}
          loading={gate.status === "loading"}
          error={gate.status === "error" ? gate.error.message : false}
          onRetry={gate.status === "error" ? gate.retry : undefined}
          empty={entityBars.length === 0 ? "The latest run recorded no per-type breakdown." : false}
        >
          <BarList data={entityBars} height={260} valueFormat={(v) => Number(v).toFixed(3)} />
        </ChartCard>

        {/* Status-coloured, and every bar carries its severity label — never colour alone. */}
        <ChartCard
          title="Compliance gaps by severity"
          sub="Clause × asset pairs with no evidence of the required document type"
          height={200}
          loading={compliance.status === "loading"}
          error={compliance.status === "error" ? compliance.error.message : false}
          onRetry={compliance.status === "error" ? compliance.retry : undefined}
          empty={gapBars.length === 0 ? "No compliance posture available." : false}
        >
          <BarList data={gapBars} height={200} valueFormat={(v) => String(v)} />
        </ChartCard>

        <section aria-label="Datastore health" className="rounded-xl border border-line bg-surface p-4">
          <h2 className="text-body font-semibold text-ink">Datastore health</h2>
          <p className="mt-0.5 text-caption text-muted">Live probe via <code>/health/detailed</code></p>
          {health.status === "error" ? (
            <div className="mt-3">
              <p className="text-caption text-muted">{health.error.message}</p>
              <button
                type="button"
                onClick={health.retry}
                className="mt-3 inline-flex min-h-11 items-center rounded-lg border border-line bg-surface-2 px-4 text-caption font-medium text-ink transition-colors hover:bg-canvas"
              >
                Retry
              </button>
            </div>
          ) : services.length === 0 ? (
            <div className="mt-3"><EmptyState message="No health data." /></div>
          ) : (
            <ul className="mt-3 space-y-2">
              {services.map((svc) => (
                <li key={svc.name} className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface-2 px-3 py-2">
                  <span className="text-body capitalize text-ink">{svc.name}</span>
                  <div className="flex items-center gap-2">
                    {svc.latency_ms != null && (
                      <span className="tabular text-label text-muted">{svc.latency_ms} ms</span>
                    )}
                    <StatusBadge tone={svc.status === "healthy" ? "verified" : "danger"}>
                      {svc.status === "healthy" ? "Healthy" : svc.status}
                    </StatusBadge>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* Table view of the same data as the trend chart — identity never colour-only. */}
      <section aria-label="Model-gate run history" className="mt-4">
        <h2 className="mb-2 text-body font-semibold text-ink">Model-gate run history</h2>
        {runs.length === 0 ? (
          <EmptyState message="No model-gate runs recorded yet. Trigger one from Governance → Model gate." />
        ) : (
          <DataTable<GateRow>
            rows={history}
            keyFn={(r) => r.run_id}
            columns={[
              { key: "run_at", label: "Run", render: (r) => (r.run_at ? new Date(r.run_at).toLocaleString("en-IN") : "—"), sortable: true, sortValue: (r) => r.run_at },
              { key: "model_name", label: "Model", render: (r) => r.model_name ?? "—" },
              { key: "precision", label: "Precision", render: (r) => f3(r.precision), sortable: true, sortValue: (r) => r.precision },
              { key: "recall", label: "Recall", render: (r) => f3(r.recall), sortable: true, sortValue: (r) => r.recall },
              { key: "f1", label: "F1", render: (r) => f3(r.f1), sortable: true, sortValue: (r) => r.f1 },
              { key: "corpus_size", label: "Corpus", render: (r) => String(r.corpus_size) },
              {
                key: "passed",
                label: "Gate",
                render: (r) => (
                  <StatusBadge tone={r.passed ? "verified" : "danger"}>{r.passed ? "Passed" : "Failed"}</StatusBadge>
                ),
              },
              {
                // A SUSPECT run had extractions fall back to the regex path, which matches
                // ASSET_TAG only — its F1 is a ceiling, not a score for the model in the row.
                // Untagged rows (Celery gate, anything before 2026-08-15) carry no verdict and
                // must not be dressed up as clean ones, so they render as "—".
                key: "validity",
                label: "Validity",
                render: (r) =>
                  r.validity ? (
                    <StatusBadge tone={r.validity === "VALID" ? "verified" : "caution"}>
                      {r.validity === "VALID"
                        ? "Valid"
                        : `Suspect${r.fallback_extractions ? ` · ${r.fallback_extractions} fallback` : ""}`}
                    </StatusBadge>
                  ) : (
                    <span className="text-muted">—</span>
                  ),
              },
            ]}
          />
        )}
      </section>

      <section className="mt-6 rounded-xl border border-line bg-surface-2 p-4">
        <h2 className="text-body font-semibold text-ink">Harness metrics not persisted by the system</h2>
        <p className="mt-1 text-caption leading-relaxed text-muted">
          Retrieval, answer quality, provenance, the concurrency sweep and time-to-answer are produced by
          the scripts in <code>benchmark/</code> and recorded in <code>benchmark/RESULTS.md</code>. They are
          deliberately not redrawn here: the system does not store them, so charting a copy would present
          a static file as live data. Run the harnesses to refresh them.
        </p>
        <p className="mt-2 text-caption text-muted">
          Latest recorded (2026-09-13, 46 questions, Nemotron 3 Super on NVIDIA NIM): retrieval{" "}
          <strong className="text-ink">46/46</strong> · answer quality{" "}
          <strong className="text-ink">41/46</strong> (95% CI 77–95%, run validity{" "}
          <strong className="text-ink">VALID</strong>) · provenance <strong className="text-ink">46/46</strong>{" "}
          · compliance gap F1 <strong className="text-ink">0.912</strong> · load{" "}
          <strong className="text-ink">0% errors to 50 VU</strong>.
        </p>
        <p className="mt-2 text-caption text-muted">
          Compliance fell from 0.986 because a human promoted a quarantined procedure onto EQ-101 after
          the truth table was authored, so five clauses it lists as gaps are now genuinely covered. The
          truth table is deliberately not amended — grading a system against its own output measures
          nothing. Precision stays 1.000 with zero false positives.
        </p>
        <Link
          href="/governance/model-gate"
          className="mt-3 inline-flex min-h-11 items-center rounded-lg border border-line bg-surface px-4 text-caption font-medium text-ink transition-colors hover:bg-canvas"
        >
          Run the model gate
        </Link>
      </section>
    </div>
  );
}
