"use client";

// Where this asset sits in the plant: its PARENT_OF ancestry and direct children.
import Link from "next/link";
import { Button } from "@/components/ui";
import { getAssetHierarchy, type HierarchyAsset } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";

function AssetLink({ asset }: { asset: HierarchyAsset }) {
  return (
    <Link href={`/assets/${asset.asset_id}`} className="tabular font-semibold text-accent hover:underline">
      {asset.asset_id}
      {asset.name && <span className="font-normal text-muted"> · {asset.name}</span>}
    </Link>
  );
}

export function HierarchyPanel({ assetId }: { assetId: string }) {
  const state = useFetch(() => getAssetHierarchy(assetId), [assetId]);

  return (
    <section data-testid="asset-hierarchy" className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
      <div className="border-b border-line px-4 py-4 sm:px-5">
        <h2 className="text-sm font-semibold text-ink">Hierarchy</h2>
        <p className="mt-0.5 text-caption text-muted">Parent chain and direct children in the facility structure.</p>
      </div>
      <div className="px-4 py-4 text-caption sm:px-5">
        {state.status === "loading" && <div className="h-20 animate-pulse rounded-lg bg-surface-2" />}
        {state.status === "error" && (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-muted">Couldn&apos;t load the hierarchy — {state.error.message}</span>
            <Button onClick={state.retry}>Retry</Button>
          </div>
        )}
        {state.status === "live" && (() => {
          // Ancestors come back root-first (by creation); render the chain down to this asset.
          const { ancestors, children } = state.data;
          return (
            <>
              <p className="text-label font-semibold uppercase tracking-[0.1em] text-muted">Parent chain</p>
              {ancestors.length === 0 ? (
                <p className="mt-1.5 text-muted">Top-level asset — no parent recorded.</p>
              ) : (
                <ol className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1">
                  {ancestors.map((a) => (
                    <li key={a.asset_id} className="flex items-center gap-1.5"><AssetLink asset={a} /><span aria-hidden="true" className="text-muted">›</span></li>
                  ))}
                  <li className="tabular font-semibold text-ink" aria-current="page">{assetId}</li>
                </ol>
              )}
              <p className="mt-4 text-label font-semibold uppercase tracking-[0.1em] text-muted">Children ({children.length})</p>
              {children.length === 0 ? (
                <p className="mt-1.5 text-muted">No child assets.</p>
              ) : (
                <ul className="mt-1.5 space-y-1">
                  {children.map((c) => <li key={c.asset_id}><AssetLink asset={c} /></li>)}
                </ul>
              )}
            </>
          );
        })()}
      </div>
    </section>
  );
}
