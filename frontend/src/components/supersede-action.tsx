"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ingestDocument, supersedeDocument } from "@/lib/api";
import { useRole, RESOLVE_ROLES } from "@/components/use-role";
import { Button, Modal } from "@/components/ui";
import type { AuthorityLevel } from "@/lib/types";

const DOC_TYPES = [
  "oem_manual", "procedure", "inspection_report", "ptw",
  "shift_log", "regulation", "pid_drawing",
] as const;

export function SupersedeAction({ documentId, assetId }: { documentId: string; assetId?: string | null }) {
  const role = useRole();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [docType, setDocType] = useState<string>("procedure");
  const [authority, setAuthority] = useState<AuthorityLevel>(3);

  if (!RESOLVE_ROLES.includes(role)) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;

    const fd = new FormData();
    fd.append("file", file);
    fd.append("document_type", docType);
    fd.append("authority_level", String(authority));
    fd.append("source_system", "manual_upload");
    // The replacement describes the same equipment, so it links to the same asset.
    if (assetId) fd.append("asset_id", assetId);

    setBusy(true);
    setError(null);
    try {
      // Two steps: the replacement enters the vault, then the old version's validity window closes.
      const ingested = await ingestDocument(fd);
      if (ingested.document_id === documentId) {
        setError("That file is identical to this document — upload the revised version.");
        return;
      }
      await supersedeDocument(documentId, ingested.document_id);
      setDone(ingested.document_id);
      // Refresh the page so the version chain + blast radius update
      router.refresh();
    } catch {
      setError("Supersede failed — the replacement could not be saved. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        variant="ghost"
        onClick={() => { setOpen(true); setDone(null); setError(null); }}
        className="text-caption"
      >
        Supersede document
      </Button>

      {open && (
        <Modal title="Supersede document" onClose={() => setOpen(false)}>
          {done ? (
            <div className="space-y-3">
              <p className="text-body text-ink">
                Document <span className="font-semibold text-accent">{documentId}</span> superseded.
                New document: <span className="font-semibold text-accent">{done}</span>.
              </p>
              <p className="text-caption text-muted">
                The blast-radius panel below now shows downstream items flagged for review.
                If any affected edge has authority ≤ 3, an MoC item may have been auto-created.
              </p>
              <Button variant="ghost" onClick={() => setOpen(false)}>Close</Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <p className="text-caption text-muted">
                Upload the replacement document. The original is retained in the vault (immutability is
                non-negotiable). All downstream knowledge edges will be flagged for review.
              </p>

              <div className="space-y-3">
                <label className="flex flex-col gap-1">
                  <span className="text-label font-semibold uppercase tracking-[0.1em] text-muted">
                    Replacement file
                  </span>
                  <input
                    ref={fileRef}
                    type="file"
                    required
                    accept=".pdf,.json,.txt,.docx"
                    className="text-caption text-muted file:mr-3 file:rounded-md file:border file:border-line file:bg-surface-2 file:px-2.5 file:py-1 file:text-label file:font-semibold file:text-ink"
                  />
                </label>

                <label className="flex flex-col gap-1">
                  <span className="text-label font-semibold uppercase tracking-[0.1em] text-muted">
                    Document type
                  </span>
                  <select
                    value={docType}
                    onChange={(e) => setDocType(e.target.value)}
                    className="h-9 rounded-lg border border-line bg-surface-2 px-2 text-caption outline-none focus:border-accent"
                  >
                    {DOC_TYPES.map((t) => (
                      <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
                    ))}
                  </select>
                </label>

                <label className="flex flex-col gap-1">
                  <span className="text-label font-semibold uppercase tracking-[0.1em] text-muted">
                    Authority level
                  </span>
                  <select
                    value={authority}
                    onChange={(e) => setAuthority(Number(e.target.value) as AuthorityLevel)}
                    className="h-9 rounded-lg border border-line bg-surface-2 px-2 text-caption outline-none focus:border-accent"
                  >
                    {[1, 2, 3, 4, 5].map((l) => (
                      <option key={l} value={l}>L{l}</option>
                    ))}
                  </select>
                </label>
              </div>

              {error && (
                <p className="text-caption text-danger">{error}</p>
              )}

              <div className="flex justify-end gap-2 pt-1">
                <Button variant="ghost" type="button" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button variant="primary" type="submit" disabled={busy}>
                  {busy ? "Uploading…" : "Confirm supersede"}
                </Button>
              </div>
            </form>
          )}
        </Modal>
      )}
    </>
  );
}
