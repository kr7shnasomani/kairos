// Vault document detail: provenance, version chain, topology link, supersede action.
import Link from "next/link";
import { notFound } from "next/navigation";
import { getDocument, getDocumentStatus, isForbidden, isNotFound } from "@/lib/api";
import { authorityLabel, relativeTime, triggerLabel } from "@/lib/utils";
import { AuthorityBadge, SourceChip, StatusBadge, Timeline, type TimelineEvent, PageHeader } from "@/components/ui";
import { BlastRadiusPanel, SupersedeAction } from "@/components/lazy";
import { ExtractionPanel } from "./extraction-panel";
import { OcrReviewActions } from "./ocr-review-actions";
import { OpenArtifactButton } from "./open-artifact";
import { RedactedExport } from "./redacted-export";
import type { VaultDocument } from "@/lib/types";

function fmtSize(bytes?: number): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function buildVersionChain(old: VaultDocument, newer: VaultDocument): TimelineEvent[] {
  return [
    {
      id: old.document_id,
      timestamp: relativeTime(old.ingested_at),
      label: old.document_id,
      description: old.file_name,
      tone: "neutral",
      meta: "superseded",
    },
    {
      id: newer.document_id,
      timestamp: relativeTime(newer.ingested_at),
      label: newer.document_id,
      description: newer.file_name,
      tone: "verified",
      meta: "active",
    },
  ];
}

export default async function DocumentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await getDocument(id).catch((e) => {
    if (isNotFound(e)) notFound();
    if (isForbidden(e)) return null;
    throw e;
  });
  if (!res) return null;
  const { data: d } = res;
  if (!d) notFound();

  // Superseding doc (version chain) and pipeline status are independent — fetch together.
  // A status failure hides only the review notice; it never blocks the document itself.
  const [supersedingDoc, status] = await Promise.all([
    d.version_chain ? getDocument(d.version_chain).then(({ data }) => data).catch(() => null) : null,
    getDocumentStatus(d.document_id).then(({ data }) => data).catch(() => null),
  ]);

  const meta: { label: string; value: React.ReactNode }[] = [
    { label: "Type", value: triggerLabel(d.document_type) },
    { label: "Source system", value: d.source_system },
    { label: "Ingested", value: `${relativeTime(d.ingested_at)} · ${d.ingested_by_name ?? d.ingested_by}` },
    { label: "File", value: `${d.mime_type ?? "—"} · ${fmtSize(d.file_size_bytes)}` },
  ];

  return (
    <div data-testid="document-detail-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/documents" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Documents
      </Link>

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
        <AuthorityBadge level={d.authority_level} />
        {d.status === "superseded"
          ? <StatusBadge tone="neutral" dot={false}>Superseded</StatusBadge>
          : <StatusBadge tone="verified">Active</StatusBadge>}
        {d.handwriting_suspect && (
          <StatusBadge tone="caution">Handwriting suspect · read from image</StatusBadge>
        )}
      </div>
      <PageHeader
        compact
        className="mt-1"
        title={<span className="tabular text-accent">{d.document_id}</span>}
        lede={d.file_name}
      />

      <div data-testid="document-detail-summary" className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {meta.map((m) => (
          <div key={m.label} className="rounded-xl border border-line bg-surface p-3.5">
            <p className="text-micro font-semibold uppercase tracking-[0.1em] text-muted">{m.label}</p>
            <p className="mt-1.5 text-caption leading-snug">{m.value}</p>
          </div>
        ))}
      </div>

      {/* The OCR gate (D1) stopped this document: nothing from it was indexed or linked, so saying
          so here is the difference between "held for review" and "a document with no facts". */}
      {status?.stage === "review_required" && (
        <div data-testid="ocr-review-held" role="status" className="mt-4 rounded-xl border border-[color-mix(in_srgb,var(--caution)_35%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_9%,var(--surface))] p-4">
          <p className="text-body font-semibold text-caution">Held for OCR review</p>
          <p className="mt-1 text-caption text-muted">
            {status.details ?? "The scan's recognised text is not reliable enough to use unreviewed."}
            {" "}Its text has not been indexed or linked into the knowledge graph, so it contributes no facts until a person reviews the scan.
          </p>
          <OcrReviewActions documentId={d.document_id} />
        </div>
      )}
      {status?.stage === "rejected" && (
        <div data-testid="ocr-review-rejected" className="mt-4 rounded-xl border border-line bg-surface p-4">
          <p className="text-body font-semibold text-ink">Rejected at OCR review</p>
          <p className="mt-1 text-caption text-muted">
            {status.details ?? "A reviewer judged the scan unreadable."} Nothing is extracted from this scan; the original stays in the vault.
          </p>
        </div>
      )}

      {d.document_type === "pid_drawing" && (
        <div className="mt-4 flex items-center justify-between rounded-xl border border-line bg-surface px-4 py-3">
          <p className="text-caption text-muted">P&ID topology available for this drawing.</p>
          <Link
            href={`/documents/${d.document_id}/topology`}
            className="text-caption font-medium text-accent hover:underline"
          >
            View topology →
          </Link>
        </div>
      )}

      {d.status === "superseded" && d.version_chain && (
        <div className="mt-4 rounded-xl border border-[color-mix(in_srgb,var(--caution)_35%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_9%,var(--surface))] p-4">
          <p className="text-caption">
            Superseded by{" "}
            <Link href={`/documents/${d.version_chain}`} className="font-semibold text-accent hover:underline">
              {d.version_chain}
            </Link>
            . The original artifact is retained — immutability is non-negotiable.
          </p>
        </div>
      )}

      <div data-testid="document-detail-layout" className="mt-6 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <main data-testid="document-evidence" className="min-w-0 space-y-6">
      <section>
        <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Provenance</h2>
        <div className="mt-2.5 space-y-2 rounded-xl border border-line bg-surface p-4 text-caption">
          <Row label="Authority">{authorityLabel(d.authority_level)}</Row>
          {d.sha256_hash && <Row label="SHA-256"><span className="tabular break-all text-muted">{d.sha256_hash}</span></Row>}
          <Row label="Vault">
            {d.vault_url
              ? <OpenArtifactButton documentId={d.document_id} />
              : <span className="text-muted">Authenticated vault URL (available live)</span>}
          </Row>
        </div>
      </section>

      <ExtractionPanel documentId={d.document_id} />

      {/* Version chain */}
      {supersedingDoc && (
        <section>
          <h2 className="mb-3 text-xs font-bold uppercase tracking-[0.1em] text-muted">
            Version chain
          </h2>
          <Timeline
            events={buildVersionChain(d, supersedingDoc)}
          />
          <div className="mt-3 rounded-xl border border-line bg-surface p-4 text-caption">
            <p className="font-semibold text-muted mb-2">Metadata comparison</p>
            <div className="grid grid-cols-2 gap-4">
              {(["authority_level", "source_system", "ingested_at", "document_type"] as const).map((k) => (
                <div key={k}>
                  <p className="text-micro font-semibold uppercase tracking-[0.1em] text-muted mb-1 capitalize">
                    {k.replace(/_/g, " ")}
                  </p>
                  <div className="flex flex-col gap-0.5">
                    <span className="text-label text-muted line-through">{String(d[k] ?? "—")}</span>
                    <span className="text-label font-semibold text-ink">{String(supersedingDoc[k] ?? "—")}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      <BlastRadiusPanel documentId={d.document_id} />
        </main>

        <aside data-testid="document-context" className="space-y-5 rounded-xl border border-line bg-surface p-4 shadow-sm lg:sticky lg:top-20">
          <section>
            <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Linked assets</h2>
            {d.asset_links && d.asset_links.length > 0 ? (
              <div className="mt-2.5 flex flex-wrap gap-2">
                {d.asset_links.map((aid) => (
                  <Link key={aid} href={`/assets/${aid}`} className="inline-flex min-h-11 items-center">
                    <SourceChip>{aid}</SourceChip>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-caption text-muted">No assets linked to this artifact.</p>
            )}
          </section>

          <RedactedExport documentId={d.document_id} />

      {/* Supersede action (engineer/admin, client-side role gate) */}
      <div className="border-t border-line pt-4">
        <p className="text-caption text-muted">
          Superseded documents are retained in the vault. This action is irreversible.
        </p>
        <div className="mt-3"><SupersedeAction documentId={d.document_id} assetId={d.asset_links?.[0] ?? null} /></div>
      </div>
        </aside>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3">
      <span className="w-20 shrink-0 text-label font-semibold uppercase tracking-[0.1em] text-muted">{label}</span>
      <span className="min-w-0 flex-1">{children}</span>
    </div>
  );
}
