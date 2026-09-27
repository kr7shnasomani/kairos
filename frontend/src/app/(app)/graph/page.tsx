"use client";

import { useState } from "react";
import { PageHeader, Timeline } from "@/components/ui";
import { KnowledgeGraph } from "@/components/knowledge-graph";
import type { KnowledgeGraphData } from "@/lib/types";
import { getKnowledgeGraph } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { cn, nowMs } from "@/lib/utils";
import { GraphLegend, validityEvents } from "./_components/legend";

// EQ-101 first — it's a canonical asset with live knowledge edges. P-101 is a tag alias; the
// endpoint resolves it but it currently carries no edges, so it renders an empty graph rather
// than an error. Kept as a pick, not the default.
const EXAMPLE_ASSETS = ["EQ-101", "V-247", "P-101"];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function GraphPage() {
  const [assetId, setAssetId] = useState("EQ-101");
  const [inputValue, setInputValue] = useState("EQ-101");
  const [asOf, setAsOf] = useState("");

  // Was a bare `.then()` with no `.catch()`. `getKnowledgeGraph` throws on failure (live-only
  // policy), so a timeout became an unhandled rejection and the summary tiles sat on
  // "Loading nodes" forever — no error, no retry. `useFetch` is the guard every other page in
  // the app already uses; it supplies the error and retry states this page was missing.
  const state = useFetch(() => getKnowledgeGraph(assetId, asOf || undefined), [assetId, asOf]);
  const graphData: KnowledgeGraphData | null = state.status === "live" ? state.data : null;

  function handleLoadGraph(id: string) {
    const trimmed = id.trim().toUpperCase();
    if (!trimmed) return;
    setAssetId(trimmed);
    setInputValue(trimmed);
  }

  function handleAsOfChange(val: string) {
    setAsOf(val);
  }

  const today = new Date(nowMs()).toISOString().split("T")[0];

  return (
    <div data-testid="graph-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader className="mb-6" eyebrow="Analyze" title="Temporal asset graph" lede="Investigate the evidence, events, and governed relationships surrounding an asset at any point in time." />

      <section data-testid="graph-summary" className="grid overflow-hidden rounded-xl border border-line bg-surface shadow-sm sm:grid-cols-3">
        <div className="border-b border-line p-4 sm:border-b-0 sm:border-r">
          <p className="text-micro font-bold uppercase tracking-[0.1em] text-muted">Selected asset</p>
          <div className="mt-1 flex items-center gap-2">
            <p className="text-title font-semibold text-ink">{assetId}</p>
            {/* `DataSource` has a single member ("live"), so the old "Demo" branch was
                unreachable — the fixture fallbacks it referred to no longer exist. The badge now
                reports whether this request actually landed. */}
            {state.status === "live" && (
              <span className="bg-accent-soft px-2 py-0.5 text-micro font-semibold text-accent">
                Live
              </span>
            )}
          </div>
          <p className="mt-1 text-label text-muted">{asOf ? `Snapshot ${asOf}` : "Current knowledge state"}</p>
        </div>
        <div className="border-b border-line p-4 sm:border-b-0 sm:border-r">
          <p className="text-micro font-bold uppercase tracking-[0.1em] text-muted">Connected knowledge</p>
          <p className="mt-1 text-title font-semibold text-ink">
            {graphData ? `${graphData.nodes.length} nodes` : state.status === "error" ? "Unavailable" : "Loading nodes"}
          </p>
          {/* A filtered view has to say it is filtered. The backend withholds facts sourced from
              test/sweep artifacts — ~79% of the active vault — and stating the count keeps the
              denominator auditable instead of quietly shrinking the graph. */}
          {graphData && graphData.excluded_test_documents > 0 ? (
            <p className="mt-1 text-label text-muted">
              {graphData.excluded_test_documents} test {graphData.excluded_test_documents === 1 ? "document" : "documents"} hidden
            </p>
          ) : (
            <p className="mt-1 text-label text-muted">Assets, evidence, events, and people</p>
          )}
        </div>
        <div className="p-4">
          <p className="text-micro font-bold uppercase tracking-[0.1em] text-muted">Relationships</p>
          <p className="mt-1 text-title font-semibold text-ink">
            {graphData
              ? `${graphData.edges.length} relationships`
              : state.status === "error" ? "Unavailable" : "Loading relationships"}
          </p>
          {state.status === "error" ? (
            <button
              type="button"
              onClick={state.retry}
              className="mt-1 text-label font-semibold text-accent hover:underline"
            >
              Retry
            </button>
          ) : (
            <p className="mt-1 text-label text-muted">Authority and validity remain visible</p>
          )}
        </div>
      </section>

      {/* Controls: asset selector + as_of */}
      <section data-testid="graph-controls" className="mt-4 grid gap-4 rounded-xl border border-line bg-surface p-4 shadow-sm md:grid-cols-[minmax(0,1fr)_auto] xl:grid-cols-[minmax(0,1fr)_auto_auto] xl:items-end">
        {/* Asset search */}
        <div className="min-w-0">
          <label htmlFor="asset-id" className="text-label font-medium text-muted">
            Asset ID
          </label>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleLoadGraph(inputValue);
            }}
            className="mt-1.5 flex min-w-0 items-center gap-2"
          >
            <input
              id="asset-id"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="e.g. P-101"
              className="h-11 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-body outline-none focus-visible:border-accent sm:max-w-xs"
            />
            <button
              type="submit"
              className="fill-sweep h-11 bg-accent px-4 text-body font-semibold text-on-accent transition-transform duration-150 ease-out active:scale-[0.98]"
            >
              <span className="relative z-10">View</span>
            </button>
          </form>
        </div>

        {/* Quick picks */}
        <div>
          <p className="text-label font-medium text-muted">Quick views</p>
          <div className="mt-1.5 flex flex-wrap gap-2">
          {EXAMPLE_ASSETS.map((id) => (
            <button
              key={id}
              onClick={() => handleLoadGraph(id)}
              className={cn(
                "min-h-11 rounded-lg border px-3 text-caption font-medium transition-colors",
                assetId === id
                  ? "border-accent bg-accent-soft text-accent"
                  : "border-line bg-surface text-muted hover:border-[color-mix(in_srgb,var(--accent)_40%,var(--line))] hover:text-ink"
              )}
            >
              {id}
            </button>
          ))}
          </div>
        </div>

        {/* Time-travel */}
        <div className="md:col-span-2 xl:col-span-1">
          <label htmlFor="graph-asof" className="text-label font-medium text-muted">
            As of (time travel)
          </label>
          <div className="mt-1.5 flex items-center gap-2">
            <input
              id="graph-asof"
              type="date"
              value={asOf}
              onChange={(e) => handleAsOfChange(e.target.value)}
              max={today}
              className="h-11 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-caption outline-none focus-visible:border-accent xl:w-44"
            />
            {asOf && (
              <button
                onClick={() => handleAsOfChange("")}
                className="min-h-11 rounded-lg px-2 text-label text-muted hover:bg-surface-2 hover:text-ink"
                aria-label="Clear time travel date"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      </section>

      <div data-testid="graph-layout" className="mt-4 grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0">
          <KnowledgeGraph assetId={assetId} asOf={asOf || undefined} height={560} />
          <p className="mt-2 text-label text-muted">Select a node or relationship to inspect its properties and evidence.</p>
        </div>

        {/* Height-matched to the 560px graph canvas; validity list scrolls internally
            so the panel never grows taller than the graph. */}
        <aside data-testid="graph-context" className="flex flex-col gap-4 lg:sticky lg:top-6 lg:h-[560px] lg:self-start">
          <section className="shrink-0 rounded-xl border border-line bg-surface p-4 shadow-sm">
            <p className="text-micro font-bold uppercase tracking-[0.1em] text-muted">Authority &amp; verification</p>
            <div className="mt-3"><GraphLegend /></div>
          </section>
          <section className="flex min-h-0 flex-1 flex-col rounded-xl border border-line bg-surface p-4 shadow-sm">
            <div className="flex shrink-0 items-center justify-between">
              <p className="text-micro font-bold uppercase tracking-[0.1em] text-muted">Validity windows</p>
              {graphData?.edges.length ? <span className="tabular text-label text-muted">{graphData.edges.length}</span> : null}
            </div>
            {/* overflow-x-hidden: `overflow-y-auto` alone leaves overflow-x computed as `auto`,
                which draws a stray horizontal scrollbar. Same fix as management/signals-feed.tsx. */}
            <div className="mt-3 min-h-0 flex-1 overflow-y-auto overflow-x-hidden pr-1">
              {graphData?.edges.length
                ? <Timeline events={validityEvents(graphData.edges, (id) => graphData.nodes.find((n) => n.id === id)?.label)} />
                : <p className="text-label text-muted">Relationship windows appear when graph data is available.</p>}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
