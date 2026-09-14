"use client";

// Reviewer decision for a document the OCR gate held. Human-only (reliability/admin, like quarantine
// promotion): the reviewer opens the original scan, then releases it for extraction or rejects it.
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Modal } from "@/components/ui";
import { PROMOTE_ROLES, useRole } from "@/components/use-role";
import { rejectHeldDocument, releaseHeldDocument } from "@/lib/api";

type Decision = "release" | "reject";

const COPY: Record<Decision, { title: string; body: string; confirm: string; done: string }> = {
  release: {
    title: "Release for extraction",
    body: "You have checked the original scan and it is legible. Extraction runs again past the confidence gate. What it reads still enters the graph unverified, and low-confidence entities still go to quarantine.",
    confirm: "Release scan",
    done: "Released — extraction is running again.",
  },
  reject: {
    title: "Reject scan",
    body: "The scan is not legible enough to extract from. Nothing is read from it. The original stays in the vault; ingest a clearer rescan as a new document.",
    confirm: "Reject scan",
    done: "Rejected — nothing will be extracted from this scan.",
  },
};

export function OcrReviewActions({ documentId }: { documentId: string }) {
  const role = useRole();
  const router = useRouter();
  const [open, setOpen] = useState<Decision | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  if (!PROMOTE_ROLES.includes(role)) {
    return <p className="mt-2 text-caption text-muted">A reliability engineer or admin decides whether to release or reject it.</p>;
  }
  if (done) return <p role="status" className="mt-3 text-caption font-semibold text-ink">{done}</p>;

  async function decide(decision: Decision) {
    setBusy(true);
    setError(null);
    try {
      await (decision === "release" ? releaseHeldDocument : rejectHeldDocument)(documentId, note.trim());
      setOpen(null);
      setDone(COPY[decision].done);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The decision was not saved. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="primary" onClick={() => { setOpen("release"); setError(null); }}>Release for extraction</Button>
        <Button onClick={() => { setOpen("reject"); setError(null); }}>Reject scan</Button>
      </div>
      {open && (
        <Modal title={COPY[open].title} onClose={() => !busy && setOpen(null)}>
          <p className="text-body text-muted">{COPY[open].body}</p>
          <label className="mt-4 flex flex-col gap-1 text-caption">
            <span className="font-semibold text-ink">Review note</span>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={1000} placeholder="optional — recorded in the audit trail" className="rounded-lg border border-line bg-surface px-2.5 py-2 text-body" />
          </label>
          {error && <p role="alert" className="mt-3 text-caption text-danger">{error}</p>}
          <div className="mt-4 flex justify-end gap-2">
            <Button onClick={() => setOpen(null)} disabled={busy}>Cancel</Button>
            <Button variant={open === "reject" ? "danger" : "primary"} onClick={() => decide(open)} disabled={busy}>
              {busy ? "Saving…" : COPY[open].confirm}
            </Button>
          </div>
        </Modal>
      )}
    </>
  );
}
