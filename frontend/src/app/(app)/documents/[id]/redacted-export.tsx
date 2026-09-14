"use client";

// PII-redacted export (DPDP Act 2023 boundary). Redaction happens here, at export — never at
// ingestion — and the vault original is untouched. Every export is written to the audit log.
import { useState } from "react";
import { Button } from "@/components/ui";
import { getRedactedDocument, type RedactedExport as Export } from "@/lib/api";

export function RedactedExport({ documentId }: { documentId: string }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Export | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await getRedactedDocument(documentId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed.");
    } finally {
      setBusy(false);
    }
  }

  function download() {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([result.redacted_text], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${documentId}-redacted.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function copy() {
    if (!result) return;
    await navigator.clipboard.writeText(result.redacted_text);
    setCopied(true);
  }

  const counts = result ? Object.entries(result.pii_counts).filter(([, n]) => n > 0) : [];

  return (
    <section data-testid="redacted-export" className="border-t border-line pt-4">
      <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Redacted export</h2>
      <p className="mt-2 text-caption text-muted">Text with names and identifiers masked for sharing outside the site. The export is audited.</p>
      <Button className="mt-3 w-full" onClick={run} disabled={busy}>{busy ? "Redacting…" : result ? "Export again" : "Export redacted text"}</Button>
      {error && <p role="alert" className="mt-2 text-caption text-danger">{error}</p>}
      {result && (
        <div className="mt-3 space-y-2">
          <p role="status" className="text-caption text-ink">
            {result.pii_found ? `${result.pii_span_count} identifiers masked` : "No personal identifiers found"}
          </p>
          {counts.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {counts.map(([type, n]) => (
                <span key={type} className="tabular rounded-md border border-line bg-surface-2 px-2 py-0.5 text-label text-muted">{type.replace(/_/g, " ")} · {n}</span>
              ))}
            </div>
          )}
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-surface-2 p-2.5 text-label leading-relaxed text-ink">{result.redacted_text || "(no text)"}</pre>
          <div className="flex gap-2">
            <Button className="flex-1" onClick={copy}>{copied ? "Copied" : "Copy"}</Button>
            <Button className="flex-1" onClick={download}>Download .txt</Button>
          </div>
        </div>
      )}
    </section>
  );
}
