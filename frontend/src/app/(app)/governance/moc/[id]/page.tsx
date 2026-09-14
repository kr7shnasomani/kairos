"use client";

// MoC detail: conflicting sources, draft EWR, engineer sign-off, blast radius.
import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import type { MocItem, ConflictSource } from "@/lib/types";
import { getMoc, approveMoc } from "@/lib/api";
import { relativeTime } from "@/lib/utils";
import { StatusBadge, PageHeader } from "@/components/ui";
import { DetailSkeleton } from "@/components/skeleton";
import { BlastRadiusPanel } from "@/components/lazy";

const STATUS_TONE: Record<string, "caution" | "verified" | "danger"> = {
  draft: "caution",
  pending: "caution",
  pending_approval: "caution",
  approved: "verified",
  rejected: "danger",
};

export default function MocDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [moc, setMoc] = useState<MocItem | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getMoc(id).then(({ data }) => {
      if (!alive) return;
      // Live-only: no fixture stand-in for a real MoC case.
      if (!data) { setLoadFailed(true); return; }
      setLoadFailed(false);
      setMoc(data);
    }).catch(() => { if (alive) setLoadFailed(true); });
    return () => { alive = false; };
  }, [id, reload]);

  async function handleApprove() {
    if (!moc) return;
    setBusy(true);
    setError(null);
    try {
      await approveMoc(moc.moc_id, note || undefined);
      setMoc({ ...moc, status: "approved" });
    } catch {
      setError("Approval failed — backend offline or rejected.");
    } finally {
      setBusy(false);
    }
  }

  if (loadFailed) {
    return (
      <div className="mx-auto max-w-[1400px]">
        <Link href="/governance/moc" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>
          MoC queue
        </Link>
        <div className="mt-6 rounded-xl border border-line bg-surface p-8 text-center">
          <p className="text-body font-medium text-ink">Couldn&apos;t load this MoC case.</p>
          <p className="mt-1 text-caption text-muted">Live data is unavailable.</p>
          <button type="button" onClick={() => setReload((r) => r + 1)} className="mt-4 inline-flex min-h-11 items-center rounded-lg border border-line bg-surface-2 px-4 text-caption font-medium text-ink transition-colors hover:bg-canvas">Retry</button>
        </div>
      </div>
    );
  }

  if (!moc) {
    return (
      <div className="mx-auto max-w-[1400px]">
        <DetailSkeleton />
      </div>
    );
  }

  // Backend lifecycle is draft → pending_approval → approved | rejected. Checking for "pending" (a status
  // the API never returns) sent every auto-drafted MoC to the else branch: no Approve button, and a
  // footer that read "Rejected".
  const isPending = moc.status !== "approved" && moc.status !== "rejected";

  return (
    <div data-testid="moc-case-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/governance/moc" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        MoC queue
      </Link>

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
        <StatusBadge tone={STATUS_TONE[moc.status] ?? "neutral"}>{moc.status}</StatusBadge>
      </div>
      <PageHeader
        compact
        className="mt-1"
        title={<span className="tabular text-accent">{moc.moc_id}</span>}
        actions={<span className="tabular text-label text-muted">{relativeTime(moc.created_at)}</span>}
        lede={
          <>
            Parameter discrepancy on <Link href={`/assets/${moc.asset_id}`} className="font-semibold text-accent hover:underline">{moc.asset_id}</Link>:{" "}
            <span className="font-medium">{moc.parameter ? moc.parameter.replace(/_/g, " ") : (moc.description ?? "—")}</span>
          </>
        }
      />

      <div data-testid="moc-case-layout" className="mt-5 grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div data-testid="moc-evidence" className="min-w-0 space-y-4">
      {/* Source comparison */}
      <section className="rounded-xl border border-line bg-surface p-4 shadow-sm">
        <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Conflicting sources</h2>
        <div className="mt-2.5 grid gap-2 sm:grid-cols-2">
          {([
            { s: moc.source_a as ConflictSource, tag: "A" },
            { s: moc.source_b as ConflictSource, tag: "B" },
          ]).map(({ s, tag }) => (
            <div key={tag} className="rounded-lg border border-line bg-surface-2 p-3">
              <span className="tabular text-label font-semibold text-muted">Source {tag}</span>
              <p className="mt-1 text-body font-medium">{String(s?.value ?? "—")}</p>
              {s?.document_id && (
                <Link
                  href={`/documents/${s.document_id}`}
                  className="tabular mt-0.5 block text-label text-accent hover:underline"
                >
                  {typeof s.file_name === "string" ? s.file_name : s.document_id}
                </Link>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Draft EWR content */}
      {moc.draft_content && (
        <section className="rounded-xl border border-line bg-surface p-4 shadow-sm">
          <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Auto-drafted EWR</h2>
          <div className="mt-2.5 rounded-lg bg-surface-2 p-4 text-body leading-relaxed text-ink">
            {moc.draft_content}
          </div>
          <p className="mt-1.5 text-label text-muted">
            Draft generated by Kairos. Requires engineer sign-off — never auto-approved.
          </p>
        </section>
      )}

          {(moc.blast_radius_count ?? 0) > 0 && (
            <section className="rounded-xl border border-line bg-surface p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Downstream impact</h2>
                <span className="tabular text-caption font-semibold text-danger">{moc.blast_radius_count} flagged</span>
              </div>
              <BlastRadiusPanel documentId={(moc.source_b as ConflictSource)?.document_id ?? moc.moc_id} />
            </section>
          )}
        </div>

        <aside data-testid="moc-decision" className="lg:sticky lg:top-20">

      {/* Approval */}
      {isPending && (
        <section className="rounded-xl border border-[color-mix(in_srgb,var(--caution)_30%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_6%,var(--surface))] p-4 shadow-sm">
          <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Engineer sign-off</h2>
          <p className="mt-2 text-caption text-muted">
            Approving this MoC closes the validity window of the old edge and clears downstream warning banners.
            This action is irreversible and logged.
          </p>
          <div className="mt-3 flex flex-col gap-2.5">
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Engineer note (optional)"
              aria-label="Engineer note"
              className="h-11 rounded-lg border border-line bg-surface px-3 text-caption outline-none focus:border-accent"
            />
            {error && <p className="text-caption text-danger">{error}</p>}
            <div className="flex flex-col gap-2 sm:flex-row lg:flex-col">
              <button
                onClick={handleApprove}
                disabled={busy}
                className="inline-flex min-h-11 items-center justify-center rounded-lg bg-accent px-4 text-caption font-semibold text-on-accent transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {busy ? "Approving…" : "Approve MoC"}
              </button>
              <Link
                href="/governance/conflicts"
                className="inline-flex min-h-11 items-center justify-center rounded-lg border border-line px-4 text-caption font-semibold text-muted transition-colors hover:bg-surface hover:text-ink"
              >
                View conflict
              </Link>
            </div>
          </div>
        </section>
      )}

      {!isPending && (
        <div className="flex items-center gap-2 rounded-xl border border-line bg-surface px-4 py-4 shadow-sm">
          <span className={`inline-flex items-center gap-1.5 text-body font-semibold ${moc.status === "approved" ? "text-verified" : "text-danger"}`}>
            <span className={`size-2 rounded-full ${moc.status === "approved" ? "bg-verified" : "bg-danger"}`} aria-hidden="true" />
            {moc.status === "approved" ? "Approved — downstream facts cleared" : "Rejected"}
          </span>
        </div>
      )}
        </aside>
      </div>
    </div>
  );
}
