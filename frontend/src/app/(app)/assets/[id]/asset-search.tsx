"use client";

// Hybrid search locked to one asset's knowledge.
import Link from "next/link";
import { useState } from "react";
import { AuthorityBadge, Button } from "@/components/ui";
import { searchAsset, type AssetSearchHit } from "@/lib/api";

export function AssetSearch({ assetId }: { assetId: string }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [hits, setHits] = useState<AssetSearchHit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setHits(await searchAsset(assetId, q.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section data-testid="asset-search" className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
      <div className="border-b border-line px-4 py-4 sm:px-5">
        <h2 className="text-sm font-semibold text-ink">Search this asset</h2>
        <p className="mt-0.5 text-caption text-muted">Documents linked to {assetId}, ranked by authority then relevance.</p>
      </div>
      <div className="px-4 py-4 sm:px-5">
        <form onSubmit={submit} className="flex gap-2">
          <input
            type="search"
            aria-label={`Search ${assetId}`}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. seal failure, inspection interval"
            className="h-9 min-w-0 flex-1 rounded-lg border border-line bg-surface px-2.5 text-body"
          />
          <Button type="submit" variant="primary" disabled={busy || !q.trim()}>{busy ? "Searching…" : "Search"}</Button>
        </form>
        {error && <p role="alert" className="mt-3 text-caption text-danger">{error}</p>}
        {hits && hits.length === 0 && <p className="mt-3 text-caption text-muted">No documents for {assetId} match that query.</p>}
        {hits && hits.length > 0 && (
          <ul className="mt-3 divide-y divide-line">
            {hits.map((h) => (
              <li key={h.document_id} className="py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <AuthorityBadge level={h.authority_level} />
                  <Link href={`/documents/${h.document_id}`} className="min-w-0 truncate text-caption font-semibold text-accent hover:underline">{h.title || h.document_id}</Link>
                </div>
                {h.snippet && <p className="mt-1 line-clamp-2 text-caption text-muted">{h.snippet}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
