"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { VaultDocument } from "@/lib/types";
import { getDocument } from "@/lib/api";
import { AuthorityBadge, Button, EmptyState, StatusBadge, PageHeader } from "@/components/ui";
import { PageSkeleton } from "@/components/skeleton";
import { authorityLabel, triggerLabel, relativeTime } from "@/lib/utils";

import { Icon } from "@/components/icon";
export default function CompareRoute() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <ComparePage />
    </Suspense>
  );
}

function ComparePage() {
  const sp = useSearchParams();
  const [idA, setIdA] = useState(sp.get("a") ?? "");
  const [idB, setIdB] = useState(sp.get("b") ?? "");
  const [docA, setDocA] = useState<VaultDocument | null>(null);
  const [docB, setDocB] = useState<VaultDocument | null>(null);
  const [busy, setBusy] = useState(false);

  async function compare() {
    setBusy(true);
    try {
      const [a, b] = await Promise.all([
        idA.trim() ? getDocument(idA.trim()) : Promise.resolve({ data: null }),
        idB.trim() ? getDocument(idB.trim()) : Promise.resolve({ data: null }),
      ]);
      setDocA(a.data);
      setDocB(b.data);
    } finally {
      setBusy(false);
    }
  }

  // Prefill compare from ?a=&b= without a synchronous setState in the effect body.
  useEffect(() => {
    const a = sp.get("a"), b = sp.get("b");
    if (!a || !b) return;
    let alive = true;
    (async () => {
      const [ra, rb] = await Promise.all([getDocument(a), getDocument(b)]);
      if (!alive) return;
      setDocA(ra.data);
      setDocB(rb.data);
    })();
    return () => { alive = false; };
  }, [sp]);

  return (
    <div data-testid="compare-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/documents" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <Icon name="caret-left" size={15} />
        Documents
      </Link>

      <PageHeader className="mt-4" eyebrow="Knowledge" title="Compare versions" lede="Walk the supersede chain and diff metadata across two versions. A superseded document is never presented as current. Supersession closes a validity window; it does not erase." />

      <div data-testid="compare-toolbar" className="mt-6 rounded-xl border border-line bg-surface p-4 shadow-sm sm:p-5">
        <div className="mb-3">
          <p className="text-label font-semibold uppercase tracking-[0.1em] text-accent">Select evidence</p>
          <p className="mt-1 text-body text-muted">Enter two immutable document IDs to align their metadata and highlight changes.</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto] sm:items-end">
        <label className="block min-w-0 text-caption">
          <span className="font-semibold text-ink">Document A</span>
          <input value={idA} onChange={(e) => setIdA(e.target.value)} placeholder="DOC-001"
            className="mt-1 min-h-11 w-full rounded-lg border border-line bg-surface px-3 text-body sm:min-h-9" />
        </label>
        <span className="hidden h-9 items-center text-muted sm:flex" aria-hidden="true">⇄</span>
        <label className="block min-w-0 text-caption">
          <span className="font-semibold text-ink">Document B</span>
          <input value={idB} onChange={(e) => setIdB(e.target.value)} placeholder="DOC-002"
            className="mt-1 min-h-11 w-full rounded-lg border border-line bg-surface px-3 text-body sm:min-h-9" />
        </label>
        <Button variant="primary" onClick={compare} disabled={busy || !idA || !idB}>
          {busy ? "Loading…" : "Compare"}
        </Button>
        </div>
      </div>

      {docA || docB ? (
        <CompareMatrix docA={docA} docB={docB} />
      ) : (
        <div className="mt-6">
          <EmptyState message="Enter two document IDs above to compare their versions." />
        </div>
      )}
    </div>
  );
}

function CompareMatrix({ docA, docB }: { docA: VaultDocument | null; docB: VaultDocument | null }) {
  const rows = [
    { key: "file", label: "Filename", a: docA?.file_name, b: docB?.file_name },
    { key: "type", label: "Document type", a: docA ? triggerLabel(docA.document_type) : undefined, b: docB ? triggerLabel(docB.document_type) : undefined },
    { key: "authority", label: "Authority", a: docA ? authorityLabel(docA.authority_level) : undefined, b: docB ? authorityLabel(docB.authority_level) : undefined },
    { key: "source", label: "Source system", a: docA?.source_system, b: docB?.source_system },
    { key: "ingested", label: "Ingested", a: docA ? relativeTime(docA.ingested_at) : undefined, b: docB ? relativeTime(docB.ingested_at) : undefined, rawA: docA?.ingested_at, rawB: docB?.ingested_at },
    { key: "by", label: "Ingested by", a: docA?.ingested_by, b: docB?.ingested_by },
    { key: "assets", label: "Linked assets", a: docA?.asset_links?.join(", ") || "None", b: docB?.asset_links?.join(", ") || "None" },
    { key: "hash", label: "SHA-256", a: shortHash(docA?.sha256_hash), b: shortHash(docB?.sha256_hash), rawA: docA?.sha256_hash, rawB: docB?.sha256_hash },
    { key: "chain", label: "Supersession chain", a: docA?.version_chain || "None", b: docB?.version_chain || "None" },
  ];

  return (
    <section data-testid="document-compare-matrix" className="mt-6 overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
      <div className="grid grid-cols-2 bg-surface-2 md:grid-cols-[minmax(120px,0.45fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <div className="hidden border-r border-line p-4 md:block">
          <p className="text-label font-semibold uppercase tracking-[0.1em] text-muted">Compared field</p>
        </div>
        <DocumentColumnHeader doc={docA} label="A" />
        <DocumentColumnHeader doc={docB} label="B" />
      </div>
      <div className="divide-y divide-line">
        {rows.map((row) => {
          const rawA = row.rawA ?? row.a;
          const rawB = row.rawB ?? row.b;
          const changed = docA != null && docB != null && rawA !== rawB;
          return <ComparisonRow key={row.key} rowKey={row.key} label={row.label} a={row.a} b={row.b} changed={changed} />;
        })}
      </div>
    </section>
  );
}

function DocumentColumnHeader({ doc, label }: { doc: VaultDocument | null; label: "A" | "B" }) {
  return (
    <div className="min-w-0 border-r border-line p-4 last:border-r-0">
      <p className="text-label font-semibold uppercase tracking-[0.1em] text-muted">Document {label}</p>
      {doc ? (
        <>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className="tabular truncate text-body font-semibold text-accent">{doc.document_id}</span>
            <StatusBadge tone={doc.status === "superseded" ? "caution" : "verified"} dot={false}>{doc.status}</StatusBadge>
            <AuthorityBadge level={doc.authority_level} />
          </div>
          <Link href={`/documents/${doc.document_id}`} className="mt-2 inline-flex min-h-9 items-center text-caption font-medium text-accent hover:underline">Open document {label} ↗</Link>
        </>
      ) : <p className="mt-2 text-body text-muted">Document {label} not found</p>}
    </div>
  );
}

function ComparisonRow({ rowKey, label, a, b, changed }: { rowKey: string; label: string; a?: string; b?: string; changed: boolean }) {
  const changedClass = changed ? "bg-[color-mix(in_srgb,var(--caution)_10%,transparent)]" : "";
  return (
    <div data-testid={`compare-row-${rowKey}`} className="grid grid-cols-2 md:grid-cols-[minmax(120px,0.45fr)_minmax(0,1fr)_minmax(0,1fr)]">
      <div className="col-span-2 border-b border-line bg-surface-2 px-4 py-2 md:col-span-1 md:border-b-0 md:border-r">
        <span className="text-label font-semibold uppercase tracking-[0.08em] text-muted">{label}</span>
      </div>
      <div data-testid={`compare-value-${rowKey}-a`} className={`min-w-0 border-r border-line px-4 py-3 ${changedClass}`}>
        <span className="mb-1 block text-micro font-semibold uppercase text-muted md:hidden">A</span>
        <span className="tabular break-words text-caption font-medium text-ink">{a ?? "—"}</span>
      </div>
      <div data-testid={`compare-value-${rowKey}-b`} className={`min-w-0 px-4 py-3 ${changedClass}`}>
        <span className="mb-1 block text-micro font-semibold uppercase text-muted md:hidden">B</span>
        <span className="tabular break-words text-caption font-medium text-ink">{b ?? "—"}</span>
      </div>
    </div>
  );
}

function shortHash(hash?: string) {
  return hash ? `${hash.slice(0, 12)}…` : "Not available";
}
