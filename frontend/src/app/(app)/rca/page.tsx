"use client";

import { useState } from "react";
import { Button, EvidenceLineage, PageHeader, RefusalCard } from "@/components/ui";
import { Card } from "@/components/ui-card";
import { DetailSkeleton } from "@/components/skeleton";
import { getRcaPack } from "@/lib/api";
import { useScrollReveal } from "@/lib/motion";
import { nowMs } from "@/lib/utils";
import { RCA_PRESETS } from "@/lib/rca";
import type { BriefSource, RcaPack } from "@/lib/types";
import { HypothesesPanel } from "./_components/hypotheses-panel";
import { ResultHeader } from "./_components/result-header";
import { SupportingDocs } from "./_components/supporting-docs";
import { TimelineCard } from "./_components/timeline-card";

function docsToBriefSources(pack: RcaPack): BriefSource[] {
  return (pack.supporting_documents ?? []).map((d) => ({
    document_id: d.document_id,
    document_type: "document",
    title: d.title,
    authority_level: d.authority_level,
    relevant_excerpt: "",
    vault_url: null,
    is_quarantine: false,
  }));
}

export default function RcaPage() {
  const [asset, setAsset] = useState("EQ-101");
  const [code, setCode] = useState("SEAL-FAIL");
  const [today] = useState(() => new Date(nowMs()).toISOString().slice(0, 10));
  const [incidentDate, setIncidentDate] = useState(today);
  const [includeQuarantine, setIncludeQuarantine] = useState(false);
  const [pack, setPack] = useState<RcaPack | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  function assemble(a = asset, c = code, d = incidentDate, q = includeQuarantine) {
    setAsset(a);
    setCode(c);
    setLoading(true);
    setPack(null);
    setFailed(false);
    getRcaPack(a, c, `${d}T00:00:00Z`, q)
      .then((p) => setPack(p))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }

  return (
    <div data-testid="rca-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader eyebrow="Layer 11 · Root Cause" title="RCA workspace" lede="Assemble failure timelines, evidence-weighted hypotheses, and supporting documents for engineering review." />

      <form
        data-testid="rca-builder"
        onSubmit={(e) => { e.preventDefault(); assemble(); }}
        className="mt-6 rounded-xl border border-line bg-surface p-4 shadow-sm sm:p-5"
      >
        <div>
          <h2 className="text-sm font-semibold text-ink">Build an investigation pack</h2>
          <p className="mt-0.5 text-caption text-muted">Select the incident context to assemble evidence from connected systems.</p>
        </div>
        <div data-testid="rca-builder-fields" className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(140px,0.7fr)_minmax(180px,1fr)_180px_auto] lg:items-end">
          <label className="grid gap-1">
            <span className="text-label font-semibold text-muted">Asset</span>
            <input
              value={asset}
              onChange={(e) => setAsset(e.target.value)}
              className="tabular h-11 w-full rounded-lg border border-line bg-surface px-3 text-body outline-none focus:border-accent lg:h-9"
            />
          </label>
          <label className="grid gap-1">
            <span className="text-label font-semibold text-muted">Failure code</span>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="tabular h-11 w-full rounded-lg border border-line bg-surface px-3 text-body outline-none focus:border-accent lg:h-9"
            />
          </label>
          <label className="grid gap-1">
            <span className="text-label font-semibold text-muted">Incident date</span>
            <input
              type="date"
              required
              value={incidentDate}
              onChange={(e) => setIncidentDate(e.target.value)}
              max={today}
              className="h-11 w-full rounded-lg border border-line bg-surface px-3 text-caption outline-none focus:border-accent lg:h-9"
            />
          </label>
          <Button variant="primary" type="submit" className="h-11 sm:col-span-2 lg:col-span-1 lg:h-9">
            Assemble RCA pack
          </Button>
        </div>

        <label className="mt-4 flex min-h-11 cursor-pointer items-center gap-2 text-caption text-muted sm:min-h-0">
          <input
            type="checkbox"
            checked={includeQuarantine}
            onChange={(e) => setIncludeQuarantine(e.target.checked)}
            className="size-3.5 rounded accent-accent"
          />
          Include unverified quarantine data (field observations, voice notes)
        </label>
      </form>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-label font-semibold text-muted">Example investigations</span>
        {RCA_PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => assemble(p.asset_id, p.failure_code)}
            className="min-h-9 rounded-full border border-line bg-surface px-3 py-1.5 text-caption text-muted transition-colors hover:border-[color-mix(in_srgb,var(--accent)_40%,var(--line))] hover:text-accent"
          >
            {p.label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="mt-6">
          {/* The client budget for this call is 90s because the pack genuinely takes that long
              (NIM synthesis over the whole timeline). Say so — an unexplained 90s skeleton reads as a hung page, which is the
              same wrong conclusion the old 8s abort produced, just slower. */}
          <p className="text-caption text-muted" role="status">
            Assembling the pack — synthesis runs against the full evidence set and can take up to
            90 seconds.
          </p>
          <div className="mt-3"><DetailSkeleton /></div>
        </div>
      )}

      {failed && (
        <Card className="mt-6 p-4 sm:p-5">
          <p className="text-body text-ink">Could not assemble the RCA pack.</p>
          <Button variant="ghost" className="mt-3" onClick={() => assemble()}>Retry</Button>
        </Card>
      )}

      {pack && <RcaResult pack={pack} />}
    </div>
  );
}

function RcaResult({ pack }: { pack: RcaPack }) {
  const { ref: gridRef, revealed: gridRevealed } = useScrollReveal<HTMLDivElement>();
  const { ref: lowerRef, revealed: lowerRevealed } = useScrollReveal<HTMLDivElement>();
  const revealCls = (revealed: boolean) =>
    `min-w-0 transition-all duration-500 ${revealed ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"}`;
  const briefSources = docsToBriefSources(pack);

  return (
    <div className="mt-6 space-y-6">
      <ResultHeader pack={pack} />

      {pack.refused ? (
        <RefusalCard
          reason="This failure code is safety-critical. Kairos does not synthesize hypotheses — source documents are returned directly for engineer review."
          sources={briefSources}
          escalateTo="Reliability Engineer or Plant Safety Officer"
        />
      ) : (
        <>
          {!pack.synthesis_available && (
            <div className="rounded-xl border border-[color-mix(in_srgb,var(--caution)_35%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_8%,var(--surface))] px-4 py-3">
              <p className="text-caption text-ink">
                <span className="font-semibold">Synthesis unavailable</span> — raw event timeline shown.
                The graph may lack sufficient history for this failure code.
              </p>
            </div>
          )}

          {/* Two independent column stacks — supporting docs pull up under the
              timeline instead of stranding blank space beside the hypotheses. */}
          <div ref={gridRef} data-testid="rca-result-grid" className={`grid items-start gap-6 lg:grid-cols-[3fr_2fr] ${revealCls(gridRevealed)}`}>
            <div className="space-y-6">
              <TimelineCard pack={pack} />
              <SupportingDocs docs={pack.supporting_documents ?? []} />
            </div>
            <HypothesesPanel hypotheses={pack.hypotheses ?? []} />
          </div>

          <div ref={lowerRef} className={revealCls(lowerRevealed)} style={{ transitionDelay: lowerRevealed ? "100ms" : "0ms" }}>
            <EvidenceLineage sources={briefSources} />
          </div>
        </>
      )}
    </div>
  );
}
