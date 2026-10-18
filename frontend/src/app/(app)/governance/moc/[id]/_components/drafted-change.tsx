"use client";

import Link from "next/link";
import { useState } from "react";
import { draftMoc } from "@/lib/api";
import type { MocDraft } from "@/lib/types";
import { relativeTime } from "@/lib/utils";
import { Button, SourceChip } from "@/components/ui";

/** The drafted redline for a MoC: where each affected document states the old value, and the cited change. */
export function DraftedChange({
  mocId,
  draft: initial,
  generatedAt: initialAt,
  canDraft,
}: {
  mocId: string;
  draft: MocDraft | null | undefined;
  generatedAt: string | null | undefined;
  canDraft: boolean;
}) {
  const [draft, setDraft] = useState(initial ?? null);
  const [generatedAt, setGeneratedAt] = useState(initialAt ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDraft() {
    setBusy(true);
    setError(null);
    try {
      const res = await draftMoc(mocId);
      setDraft(res.draft);
      setGeneratedAt(res.draft_generated_at);
    } catch {
      setError("No draft came back. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!draft && !canDraft) return null;
  return (
    <section data-testid="moc-drafted-change" className="rounded-xl border border-line bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Drafted change</h2>
        {canDraft && (
          <Button variant="ghost" onClick={handleDraft} disabled={busy} className="min-h-11 text-caption">
            {busy ? "Drafting…" : draft ? "Redraft" : "Draft the change"}
          </Button>
        )}
      </div>
      {error && <p className="mt-2 text-caption text-danger">{error}</p>}
      {!draft ? (
        <p className="mt-2 text-caption text-muted text-pretty">
          Kairos reads the conflicting sources and the documents the change reaches, and drafts each edit with its citation.
        </p>
      ) : (
        <>
          {draft.summary && <p className="mt-2.5 text-body leading-relaxed text-ink text-pretty">{draft.summary}</p>}
          {draft.changes.length === 0 ? (
            <p className="mt-2 text-caption text-muted">No affected document states the value being changed.</p>
          ) : (
            <ol className="mt-3 space-y-3">
              {draft.changes.map((c, i) => (
                <li key={`${c.document_id}-${i}`} className="rounded-lg border border-line bg-surface-2 p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <Link href={`/documents/${c.document_id}`} className="text-caption font-semibold text-accent hover:underline">
                      {c.title || c.document_id}
                    </Link>
                    {c.location && <span className="text-label text-muted">{c.location}</span>}
                  </div>
                  <p className="mt-2 text-caption text-muted line-through decoration-line">{c.current}</p>
                  <p className="mt-1 text-body font-medium text-ink">{c.proposed}</p>
                  {c.reason && <p className="mt-1.5 text-caption text-muted text-pretty">{c.reason}</p>}
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {c.cited.map((d) => <SourceChip key={d}>{d}</SourceChip>)}
                  </div>
                </li>
              ))}
            </ol>
          )}
          {draft.open_questions.length > 0 && (
            <div className="mt-3">
              <p className="text-label font-semibold text-muted">For the engineer to decide</p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-caption text-ink">
                {draft.open_questions.map((q) => <li key={q}>{q}</li>)}
              </ul>
            </div>
          )}
          <p className="mt-3 text-label text-muted">
            A draft for review{generatedAt ? `, ${relativeTime(generatedAt)}` : ""}. It edits no document, and approving the MoC works as before.
          </p>
        </>
      )}
    </section>
  );
}
