"use client";

import { ConfidenceMeter, StatusBadge } from "@/components/ui";
import { Card } from "@/components/ui-card";
import type { RcaPack } from "@/lib/types";

/** Investigation-pack header: asset/failure/date identity, export, confidence + badges. */
export function ResultHeader({ pack }: { pack: RcaPack }) {
  const exportHref = `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(pack, null, 2))}`;

  return (
    <Card className="p-4 shadow-sm sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-label font-semibold uppercase tracking-[0.1em] text-muted">Investigation pack</p>
          <div className="mt-2 flex flex-wrap items-center gap-2.5">
            <span className="tabular text-subtitle font-semibold text-accent">{pack.asset_id}</span>
            <span className="tabular rounded-md border border-line bg-surface-2 px-2 py-1 text-caption font-medium text-ink">{pack.failure_code}</span>
            <span className="tabular text-caption text-muted">
              {new Date(pack.incident_date).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}
            </span>
          </div>
        </div>
        <a
          href={exportHref}
          download={`${pack.asset_id}-${pack.failure_code}-rca.json`}
          className="inline-flex h-11 shrink-0 items-center justify-center rounded-lg border border-line px-3.5 text-body font-semibold text-ink transition-colors hover:bg-surface-2 sm:h-9"
        >
          Export JSON
        </a>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
        {pack.synthesis_available ? <StatusBadge tone="verified">Synthesis available</StatusBadge> : <StatusBadge tone="caution">Timeline only</StatusBadge>}
        <div className="min-w-48 flex-1">
          {Number.isFinite(pack.confidence) ? (
            <ConfidenceMeter value={pack.confidence} />
          ) : (
            <span className="tabular text-label font-semibold text-muted">Confidence —</span>
          )}
        </div>
        <span className="tabular text-label text-muted">
          {(pack.timeline ?? []).length} events, {(pack.hypotheses ?? []).length} hypotheses, {(pack.supporting_documents ?? []).length} sources
        </span>
      </div>
    </Card>
  );
}
