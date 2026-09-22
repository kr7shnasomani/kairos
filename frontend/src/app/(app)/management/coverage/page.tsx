"use client";

import Link from "next/link";
import { useMemo } from "react";
import { DataTable, EmptyState, PageHeader, StatusBadge, type TableColumn } from "@/components/ui";
import { getAssetCoverage } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import type { AssetCoverage } from "@/lib/types";

// DataTable constrains its row to Record<string, unknown>; a plain interface has no
// index signature. Same shape, same fields -- see audit/page.tsx for the precedent.
type CoverageRow = AssetCoverage & Record<string, unknown>;
import { cn } from "@/lib/utils";

import { Icon } from "@/components/icon";
// The four dimensions the platform can honestly report per asset. "Verified" is deliberately
// included even though it reads zero across the estate today — that is the quarantine gate doing
// its job (nothing is auto-promoted), and hiding the column would hide the finding.
const DIMENSIONS = [
  { key: "facts", label: "Facts", hint: "Distinct knowledge edges on the asset" },
  { key: "authoritative_facts", label: "Authoritative", hint: "From regulatory / engineering / OEM sources (level 1-3)" },
  { key: "verified_facts", label: "Verified", hint: "Human-promoted through the quarantine gate" },
  { key: "documents", label: "Documents", hint: "Vault documents linked to the asset" },
] as const;

/** Shade a cell by its value relative to the strongest asset in that column.
 *  Relative, not absolute: "how thin is this compared with the best-covered equipment we have"
 *  is the question a reliability engineer actually asks, and an absolute scale would paint a
 *  small corpus uniformly empty and say nothing. */
function shade(value: number, max: number): string {
  if (value === 0) return "bg-surface-2 text-muted";
  const ratio = max > 0 ? value / max : 0;
  if (ratio >= 0.75) return "bg-[color-mix(in_srgb,var(--verified)_28%,var(--surface))] text-ink";
  if (ratio >= 0.4) return "bg-[color-mix(in_srgb,var(--verified)_16%,var(--surface))] text-ink";
  return "bg-[color-mix(in_srgb,var(--caution)_14%,var(--surface))] text-ink";
}

// Stable identity for the not-yet-loaded case, so `rows` does not change on
// every render while the fetch is in flight.
const EMPTY_ROWS: CoverageRow[] = [];

export default function CoveragePage() {
  const state = useFetch(() => getAssetCoverage(), []);
  // Memoised because the `[]` fallback is a fresh array on every render, which
  // would invalidate every downstream useMemo that depends on `rows`
  // (react-hooks/exhaustive-deps).
  //
  // The cast is the whole reason CoverageRow exists: an interface has no index
  // signature, so it never structurally satisfies Record<string, unknown> even
  // though every field is known. No shape change, no runtime effect.
  const rows = useMemo(
    () => (state.status === "live" ? (state.data as CoverageRow[]) : EMPTY_ROWS),
    [state],
  );

  const maxima = useMemo(() => {
    const m: Record<string, number> = {};
    for (const d of DIMENSIONS) m[d.key] = Math.max(0, ...rows.map((r) => Number(r[d.key as keyof AssetCoverage] ?? 0)));
    return m;
  }, [rows]);

  // Review items 20 and 21: DataTable brings sorting and the compact row rhythm the
  // rest of the app uses. The relative heat shading is the point of this page, so it
  // moves into `render` rather than being dropped -- and every numeric column sorts on
  // its raw value, not its rendered string.
  const columns: TableColumn<CoverageRow>[] = useMemo(
    () => [
      {
        key: "asset_id",
        label: "Asset",
        className: "w-[30%]",
        sortValue: (r) => r.asset_id,
        render: (r) => (
          <>
            <Link href={`/assets/${r.asset_id}`} className="font-medium text-link hover:underline">
              {r.asset_id}
            </Link>
            <div className="text-label text-muted">{r.name}</div>
          </>
        ),
      },
      ...DIMENSIONS.map((d) => ({
        key: d.key,
        label: d.label,
        align: "right" as const,
        sortValue: (r: CoverageRow) => Number(r[d.key as keyof AssetCoverage] ?? 0),
        render: (r: CoverageRow) => {
          const v = Number(r[d.key as keyof AssetCoverage] ?? 0);
          return (
            <span title={d.hint} className={cn("inline-block min-w-[2.5rem] rounded-lg px-2 py-1 text-center tabular font-medium", shade(v, maxima[d.key]))}>
              {v}
            </span>
          );
        },
      })),
      {
        key: "pending_quarantine",
        label: "Quarantined",
        align: "right" as const,
        sortValue: (r) => r.pending_quarantine,
        render: (r) =>
          r.pending_quarantine > 0 ? (
            <StatusBadge tone="caution" dot={false}>{r.pending_quarantine}</StatusBadge>
          ) : (
            <span className="text-muted">—</span>
          ),
      },
    ],
    [maxima],
  );

  const blindSpots = useMemo(
    () => rows.filter((r) => r.facts === 0 || r.documents === 0 || r.authoritative_facts === 0),
    [rows],
  );

  return (
    <div data-testid="coverage-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/management" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <Icon name="caret-left" size={15} />
        Overview
      </Link>

      <PageHeader
        className="mt-4"
        eyebrow="Knowledge coverage"
        title="What we know, and where we are blind"
        lede="Coverage per asset across the graph and the vault. Shading is relative to the best-covered asset — this shows where knowledge is thin, not whether it is sufficient."
      />

      {state.status === "loading" && (
        <div className="mt-6 h-64 animate-pulse rounded-xl border border-line bg-surface-2" />
      )}

      {state.status === "error" && (
        <div className="mt-6 flex flex-wrap items-center gap-3 rounded-xl border border-[color-mix(in_srgb,var(--danger)_30%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_5%,var(--surface))] p-4 text-body text-ink">
          <span>Couldn&apos;t load coverage.</span>
          <button onClick={state.retry} className="rounded-lg border border-line px-3 py-1.5 text-body hover:bg-surface-2">
            Retry
          </button>
        </div>
      )}

      {state.status === "live" && rows.length === 0 && (
        <div className="mt-6 rounded-xl border border-line bg-surface">
          <EmptyState message="No registered assets yet." />
        </div>
      )}

      {state.status === "live" && rows.length > 0 && (
        <>
          {blindSpots.length > 0 && (
            <div
              data-testid="coverage-blind-spots"
              className="mt-6 rounded-xl border border-[color-mix(in_srgb,var(--caution)_30%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_6%,var(--surface))] p-4"
            >
              <p className="text-body font-semibold text-ink">
                {blindSpots.length} asset{blindSpots.length === 1 ? "" : "s"} with a coverage blind spot
              </p>
              <p className="mt-1 text-caption leading-relaxed text-muted">
                Missing facts, no linked document, or nothing above authority level 3. These are the
                assets where a question is most likely to go unanswered — or to be answered from a
                site procedure rather than an engineering source.
              </p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {blindSpots.map((b) => (
                  <Link
                    key={b.asset_id}
                    href={`/assets/${b.asset_id}`}
                    className="border border-line bg-surface px-2.5 py-1 text-label text-ink hover:border-[color-mix(in_srgb,var(--accent)_50%,var(--line))]"
                  >
                    {b.asset_id}
                  </Link>
                ))}
              </div>
            </div>
          )}

          <div className="mt-6">
            <DataTable<CoverageRow>
              columns={columns}
              rows={rows}
              keyFn={(r) => r.asset_id}
              emptyState={<EmptyState message="No registered assets yet." />}
            />
          </div>

          <p className="mt-3 text-caption leading-relaxed text-muted">
            Counts are distinct knowledge edges, so a re-ingested asset does not appear better
            covered than it is. <strong className="font-medium text-ink">Verified reads zero across the
            estate</strong> because promotion through the quarantine gate is human-only and nothing has
            been promoted yet — the column is kept visible rather than hidden, because that is the
            finding.
          </p>
        </>
      )}
    </div>
  );
}
