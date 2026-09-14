"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { DocumentPipelineStage, DocumentStatus } from "@/lib/types";
import { ingestDocument, getDocumentStatus, type DocumentIngestResponse } from "@/lib/api";
import { useRole, RESOLVE_ROLES } from "@/components/use-role";
import { Button, StatusBadge, Timeline, PageHeader } from "@/components/ui";

// Default authority follows the dataset canon (regulation L1 … field shift log L5); the uploader can
// still override it. A flat L3 default filed SOPs and shift logs as OEM-grade evidence.
const DOC_TYPES = [
  { value: "oem_manual", label: "OEM manual / bulletin", authority: "3" },
  { value: "procedure", label: "Procedure (SOP)", authority: "4" },
  { value: "inspection_report", label: "Inspection report", authority: "4" },
  { value: "ptw", label: "Permit to work", authority: "4" },
  { value: "shift_log", label: "Shift log", authority: "5" },
  { value: "regulation", label: "Regulation", authority: "1" },
  { value: "pid_drawing", label: "P&ID drawing", authority: "3" },
] as const;

const TERMINAL_STAGES: DocumentPipelineStage[] = ["complete", "review_required", "rejected", "failed"];

const STAGE_ORDER: DocumentPipelineStage[] = ["queued", "ocr", "ner", "graph_linking", "indexing", "complete"];
const STAGE_LABEL: Record<DocumentPipelineStage, string> = {
  queued: "Queued", ocr: "OCR extraction", ner: "Entity extraction",
  graph_linking: "Graph linking", indexing: "Vector + text indexing",
  complete: "Complete", review_required: "Review required", rejected: "Rejected at review", failed: "Failed",
};

export default function IngestPage() {
  const role = useRole();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState<string>("procedure");
  const [assetId, setAssetId] = useState("");
  const [sourceSystem, setSourceSystem] = useState("manual_upload");
  const [authority, setAuthority] = useState("4");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DocumentIngestResponse | null>(null);
  const [status, setStatus] = useState<DocumentStatus | null>(null);

  const canIngest = RESOLVE_ROLES.includes(role);

  // Poll the pipeline status until it reaches a terminal stage.
  useEffect(() => {
    if (!result?.document_id) return;
    let alive = true;
    const id = result.document_id;
    const tick = async () => {
      try {
        const { data } = await getDocumentStatus(id);
        if (!alive) return;
        if (data) {
          setStatus(data);
          if (TERMINAL_STAGES.includes(data.stage)) return;
        }
      } catch {
        // One slow status read (4 s budget) used to reject here and stop polling for good, freezing
        // the timeline mid-pipeline. Keep polling on the same cadence instead.
        if (!alive) return;
      }
      setTimeout(tick, 2000);
    };
    tick();
    return () => { alive = false; };
  }, [result]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("document_type", docType);
      fd.append("source_system", sourceSystem);
      fd.append("authority_level", authority);
      if (assetId.trim()) fd.append("asset_id", assetId.trim());
      const res = await ingestDocument(fd);
      setResult(res);
    } catch {
      setError("Ingestion failed — backend offline or upload rejected.");
    } finally {
      setBusy(false);
    }
  }

  // `complete` is terminal, so every step is done — rendering it as the running step left the last row
  // on "in progress" forever. `review_required` stops after OCR (the confidence gate); `failed` has
  // nothing running.
  const running = status && !TERMINAL_STAGES.includes(status.stage) ? STAGE_ORDER.indexOf(status.stage) : -1;
  const lastDone = !status
    ? -1
    : status.stage === "complete"
      ? STAGE_ORDER.length - 1
      : status.stage === "review_required"
        ? STAGE_ORDER.indexOf("ocr")
        : running - 1;
  const timelineEvents = status
    ? STAGE_ORDER.map((s, i) => {
        const reached = i <= lastDone;
        const isCurrent = i === running;
        return {
          id: s,
          timestamp: isCurrent ? "in progress" : reached ? "done" : "pending",
          label: STAGE_LABEL[s],
          tone: (isCurrent ? "info" : reached ? "verified" : "neutral") as "info" | "verified" | "neutral",
        };
      })
    : [];

  return (
    <div data-testid="ingest-workspace" className="mx-auto max-w-[1200px]">
      <Link href="/documents" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Documents
      </Link>

      <PageHeader className="mt-4" eyebrow="Flow C · Universal document ingestion" title="Ingest a document" lede="The entry point of the platform. Files are stored byte-for-byte in the immutable vault and run through the extraction pipeline. Identical files (same SHA-256) are de-duplicated, never re-stored." />

      {!canIngest && (
        <div className="mt-5 rounded-xl border border-line bg-surface p-5 text-body text-muted">
          Document ingestion requires the <span className="font-semibold text-ink">engineer</span> or{" "}
          <span className="font-semibold text-ink">admin</span> role.
        </div>
      )}

      {canIngest && !result && (
        <form data-testid="ingest-intake" onSubmit={handleSubmit} className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.65fr)] lg:items-start">
          <div className="rounded-xl border border-line bg-surface p-4 shadow-sm sm:p-5">
            <div className="mb-4">
              <p className="text-label font-semibold uppercase tracking-[0.1em] text-accent">Source file</p>
              <h2 className="mt-1 text-subtitle font-semibold text-ink">Add evidence to the vault</h2>
            </div>
            <button
              data-testid="ingest-file-drop"
              type="button"
              onClick={() => fileRef.current?.click()}
              className="flex min-h-40 w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-line bg-surface-2 px-5 py-8 text-center transition-colors hover:border-[color-mix(in_srgb,var(--accent)_40%,var(--line))] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              <span className="grid size-11 place-items-center rounded-xl bg-surface text-muted shadow-sm" aria-hidden="true">
                <svg className="size-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
                </svg>
              </span>
              <span className="text-body font-semibold text-ink">{file ? file.name : "Choose a source file"}</span>
              <span className="text-label text-muted">{file ? `${(file.size / 1024).toFixed(0)} KB selected` : "PDF, image, scanned form, or P&ID"}</span>
            </button>
            <input ref={fileRef} type="file" className="hidden" aria-label="Document file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />

            <div data-testid="ingest-metadata" className="mt-5 border-t border-line pt-5">
              <p className="mb-3 text-label font-semibold uppercase tracking-[0.1em] text-muted">Evidence metadata</p>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-caption">
                  <span className="font-semibold text-ink">Document type</span>
                  <select
                    value={docType}
                    onChange={(e) => {
                      const next = DOC_TYPES.find((t) => t.value === e.target.value);
                      setDocType(e.target.value);
                      if (next) setAuthority(next.authority);
                    }}
                    className="mt-1 min-h-11 w-full rounded-lg border border-line bg-surface px-2.5 text-body sm:min-h-9"
                  >
                    {DOC_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </label>
                <label className="block text-caption">
                  <span className="font-semibold text-ink">Authority level</span>
                  <select value={authority} onChange={(e) => setAuthority(e.target.value)} className="mt-1 min-h-11 w-full rounded-lg border border-line bg-surface px-2.5 text-body sm:min-h-9">
                    {[1, 2, 3, 4, 5].map((l) => <option key={l} value={l}>L{l}</option>)}
                  </select>
                </label>
                <label className="block text-caption">
                  <span className="font-semibold text-ink">Asset link <span className="font-normal text-muted">(optional)</span></span>
                  <input value={assetId} onChange={(e) => setAssetId(e.target.value)} placeholder="EQ-101" className="mt-1 min-h-11 w-full rounded-lg border border-line bg-surface px-2.5 text-body sm:min-h-9" />
                </label>
                <label className="block text-caption">
                  <span className="font-semibold text-ink">Source system</span>
                  <input value={sourceSystem} onChange={(e) => setSourceSystem(e.target.value)} className="mt-1 min-h-11 w-full rounded-lg border border-line bg-surface px-2.5 text-body sm:min-h-9" />
                </label>
              </div>
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-line pt-4">
              <Button type="submit" variant="primary" disabled={!file || busy}>{busy ? "Uploading…" : "Ingest document"}</Button>
              {error && <span className="text-body text-danger">{error}</span>}
            </div>
          </div>

          <aside data-testid="ingest-guide" className="rounded-xl border border-line bg-surface p-4 shadow-sm sm:p-5">
            <p className="text-label font-semibold uppercase tracking-[0.1em] text-accent">What happens next</p>
            <ol className="mt-3 divide-y divide-line">
              {[
                ["Vault storage", "Hash, deduplicate, and retain the source byte-for-byte."],
                ["Extraction", "Read text and identify equipment, events, and technical entities."],
                ["Knowledge linking", "Connect verified evidence to the graph and search indexes."],
              ].map(([title, detail], index) => (
                <li key={title} className="flex gap-3 py-3 first:pt-1 last:pb-0">
                  <span className="tabular grid size-7 shrink-0 place-items-center rounded-full bg-surface-2 text-label font-semibold text-ink">{index + 1}</span>
                  <span><span className="block text-caption font-semibold text-ink">{title}</span><span className="mt-0.5 block text-label text-muted">{detail}</span></span>
                </li>
              ))}
            </ol>
          </aside>
        </form>
      )}

      {result && (
        <section className="mt-6">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)] lg:items-start">
          <div className="rounded-xl border border-line bg-surface p-5 shadow-sm">
            <div className="flex flex-wrap items-center gap-3">
              {result.status === "duplicate"
                ? <StatusBadge tone="caution">Already ingested</StatusBadge>
                : <StatusBadge tone="verified">Stored in vault</StatusBadge>}
              <span className="tabular text-body font-semibold text-accent">{result.document_id}</span>
            </div>
            <p className="mt-2 text-caption text-muted">
              {result.status === "duplicate"
                ? "This exact file is already in the vault, so it was not stored again."
                : "Stored unchanged and queued for extraction. Progress updates on the right."}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link href={`/documents/${result.document_id}`} className="text-caption text-accent underline hover:no-underline">Open document ↗</Link>
              {docType === "pid_drawing" && (
                <Link href={`/documents/${result.document_id}/topology`} className="text-caption text-accent underline hover:no-underline">View topology ↗</Link>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-line bg-surface p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <p className="text-label font-bold uppercase tracking-[0.1em] text-muted">Pipeline status</p>
              {status?.stage === "review_required" && <StatusBadge tone="caution">Review required</StatusBadge>}
              {status?.stage === "failed" && <StatusBadge tone="danger">Failed</StatusBadge>}
              {status?.stage === "rejected" && <StatusBadge tone="neutral">Rejected at review</StatusBadge>}
            </div>
            <div className="mt-4">
              {timelineEvents.length > 0
                ? <Timeline events={timelineEvents} />
                : <p className="text-body text-muted">Waiting for the first pipeline update…</p>}
            </div>
            {/* A held document is not a quarantine item — the review happens on the document itself. */}
            {status?.stage === "review_required" && (
              <Link href={`/documents/${result.document_id}`} className="mt-2 inline-block text-caption text-accent underline hover:no-underline">
                Held by the OCR confidence gate — review the scan on the document ↗
              </Link>
            )}
          </div>
          </div>

          <Button className="mt-4" variant="ghost" onClick={() => { setResult(null); setStatus(null); setFile(null); }}>
            Ingest another
          </Button>
        </section>
      )}
    </div>
  );
}
