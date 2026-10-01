"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ingestDocument, supersedeDocument } from "@/lib/api";
import { useRole, RESOLVE_ROLES, AUTHORITY_ASSERT_ROLES } from "@/components/use-role";
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
  // Set instead of `done` when the backend held the supersede for MoC approval (HTTP 202).
  const [pendingMoc, setPendingMoc] = useState<{ mocId: string | null; newId: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [docType, setDocType] = useState<string>("procedure");
  const [authority, setAuthority] = useState<AuthorityLevel>(3);

  if (!RESOLVE_ROLES.includes(role)) return null;
  // Levels 1 to 3 need reliability or admin; the backend caps anyone else to 4 at ingest.
  const levels = AUTHORITY_ASSERT_ROLES.includes(role) ? [1, 2, 3, 4, 5] : [4, 5];
  const level = levels.includes(authority) ? authority : 4;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;

    const fd = new FormData();
    fd.append("file", file);
    fd.append("document_type", docType);
    fd.append("authority_level", String(level));
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
      const res = await supersedeDocument(documentId, ingested.document_id);
      if (res.status === "pending_moc_approval") {
        // Nothing is superseded yet: the old document stays current until the MoC is approved.
        setPendingMoc({ mocId: res.moc_id, newId: ingested.document_id });
        return;
      }
      setDone(ingested.document_id);
      // Refresh the page so the version chain + blast radius update
      router.refresh();
    } catch (err) {
      setError(
        err instanceof Error && err.message.includes("HTTP 403")
          ? "Superseding a level 1 to 3 document needs the reliability or admin role."
          : "Supersede failed — the replacement could not be saved. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        variant="ghost"
        onClick={() => { setOpen(true); setDone(null); setPendingMoc(null); setError(null); }}
        className="text-caption"
      >
        Supersede document
      </Button>

      {open && (
        <Modal title="Supersede document" onClose={() => setOpen(false)}>
          {pendingMoc ? (
            <div className="space-y-3" role="status">
              <p className="text-body text-ink">
                Awaiting MoC approval. <span className="font-semibold text-accent">{documentId}</span> is
                still current; it is not superseded yet.
              </p>
              <p className="text-caption text-muted">
                The replacement <span className="font-semibold text-accent">{pendingMoc.newId}</span> is
                stored in the vault. Change request{" "}
                <span className="font-semibold text-accent">{pendingMoc.mocId ?? "pending"}</span> must be
                approved by a reliability engineer or admin
                {pendingMoc.mocId && (
                  <>
                    {" "}
                    on{" "}
                    <Link href={`/governance/moc/${encodeURIComponent(pendingMoc.mocId)}`} className="text-accent underline hover:no-underline">
                      the MoC page
                    </Link>
                  </>
                )}
                . After approval, repeat this supersede with the same replacement to apply it.
              </p>
              <Button variant="ghost" onClick={() => setOpen(false)}>Close</Button>
            </div>
          ) : done ? (
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
                    value={level}
                    onChange={(e) => setAuthority(Number(e.target.value) as AuthorityLevel)}
                    className="h-9 rounded-lg border border-line bg-surface-2 px-2 text-caption outline-none focus:border-accent"
                  >
                    {levels.map((l) => (
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
