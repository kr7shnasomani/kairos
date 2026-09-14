"use client";

// Conflict detail — both sources side by side with their authority, the SLA clock, the blast radius
// of the older source, and the decision: resolve (administrative) or route to MoC (engineering).
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { BlastRadiusPanel } from "@/components/lazy";
import { AuthorityBadge, Button, PageHeader, StatusBadge, statusTone } from "@/components/ui";
import { RESOLVE_ROLES, useRole } from "@/components/use-role";
import { getConflictDetail, resolveConflict } from "@/lib/api";
import type { AuthorityLevel, ConflictSource } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";
import { nowMs, relativeTime, slaCountdown } from "@/lib/utils";

const SEV_TONE: Record<string, "danger" | "caution" | "verified" | "neutral"> = { critical: "danger", major: "caution", minor: "verified" };

function SourceCard({ label, source, authority }: { label: string; source: ConflictSource; authority: AuthorityLevel }) {
  const confidence = typeof source.confidence === "number" ? source.confidence : null;
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="text-micro font-semibold uppercase tracking-[0.1em] text-muted">{label}</span>
        <AuthorityBadge level={authority} />
      </div>
      {source.value != null && <p className="tabular text-title font-semibold text-ink">{String(source.value)}</p>}
      {typeof source.source === "string" && <p className="text-caption text-muted">{source.source}</p>}
      <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 pt-2 text-caption">
        {source.document_id
          ? <Link href={`/documents/${source.document_id}`} className="tabular font-semibold text-accent hover:underline">{source.document_id}</Link>
          : <span className="text-muted">No source document recorded</span>}
        {confidence !== null && <span className="tabular text-muted">Confidence {Math.round(confidence * 100)}%</span>}
      </div>
    </div>
  );
}

export default function ConflictDetailPage() {
  const { id } = useParams<{ id: string }>();
  const state = useFetch(() => getConflictDetail(id), [id]);
  const role = useRole();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [resolved, setResolved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const back = (
    <Link href="/governance/conflicts" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>
      Conflicts
    </Link>
  );

  if (state.status === "loading") {
    return <div className="mx-auto max-w-[1400px]">{back}<div className="mt-6 h-64 animate-pulse rounded-xl bg-surface-2" /></div>;
  }
  if (state.status === "error") {
    return (
      <div className="mx-auto max-w-[1400px]">
        {back}
        <section className="mt-6 rounded-xl border border-line bg-surface p-8 text-center">
          <p className="text-body font-medium text-ink">Couldn&apos;t load this conflict.</p>
          <p className="mt-1 text-caption text-muted">{state.error.message}</p>
          <Button className="mt-4" onClick={state.retry}>Retry</Button>
        </section>
      </div>
    );
  }

  const c = state.data;
  const status = resolved ? "resolved" : c.status;
  const sla = status !== "resolved" && c.sla_due_at
    ? (c.is_overdue ? { label: "SLA overdue", tone: "text-danger" } : slaCountdown(c.sla_due_at, nowMs()))
    : null;

  async function resolve() {
    setBusy(true);
    setError(null);
    try {
      await resolveConflict(c.conflict_id, { decision: "accept_higher_authority", note: note.trim() || undefined });
      setResolved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resolution failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="conflict-detail-workspace" className="mx-auto max-w-[1400px]">
      {back}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <StatusBadge tone={c.track === "engineering" ? "danger" : "info"} dot={false}>{c.track} track</StatusBadge>
        <StatusBadge tone={SEV_TONE[c.severity] ?? "neutral"}>{c.severity}</StatusBadge>
        <StatusBadge tone={statusTone(status)}>{status.replace(/_/g, " ")}</StatusBadge>
      </div>
      <PageHeader
        compact
        className="mt-1"
        title={c.parameter.replace(/_/g, " ")}
        lede={<>
          {c.asset_id ? <Link href={`/assets/${c.asset_id}`} className="tabular font-semibold text-accent hover:underline">{c.asset_id}</Link> : "No asset"}
          {" · raised "}{relativeTime(c.created_at)}
          {sla && <> · <span className={`tabular font-semibold ${sla.tone}`}>{sla.label}</span></>}
        </>}
      />

      <div className="mt-5 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <main className="min-w-0 space-y-6">
          <section>
            <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Conflicting sources</h2>
            <div className="mt-2.5 grid gap-3 sm:grid-cols-2">
              <SourceCard label="Source A" source={c.source_a ?? {}} authority={c.authority_a} />
              <SourceCard label="Source B" source={c.source_b ?? {}} authority={c.authority_b} />
            </div>
            <p className="mt-2 text-caption text-muted">Lower authority level wins by default; a human decides what becomes canonical.</p>
          </section>
          {c.source_a?.document_id
            ? <BlastRadiusPanel documentId={c.source_a.document_id} />
            : <p className="rounded-xl border border-line bg-surface p-4 text-caption text-muted">No source document recorded, so there is no blast radius to trace.</p>}
        </main>

        <aside className="space-y-3 rounded-xl border border-line bg-surface p-4 shadow-sm lg:sticky lg:top-20">
          <h2 className="text-sm font-semibold text-ink">Decision</h2>
          <p className="tabular break-all text-label text-muted">{c.conflict_id}</p>
          {status === "resolved" ? (
            <p role="status" className="text-caption font-semibold text-verified">Resolved — the higher-authority source stands.</p>
          ) : c.track === "engineering" ? (
            <>
              <p className="text-caption text-muted">Engineering-track conflicts close only through Management of Change sign-off.</p>
              <Link href="/governance/moc" className="inline-flex h-9 items-center rounded-lg bg-accent px-3.5 text-body font-semibold text-on-accent hover:brightness-105">Open MoC queue</Link>
            </>
          ) : RESOLVE_ROLES.includes(role) ? (
            <>
              <label className="flex flex-col gap-1 text-caption">
                <span className="font-semibold text-ink">Resolution note</span>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} placeholder="optional" className="rounded-lg border border-line bg-surface px-2.5 py-2 text-body" />
              </label>
              <Button variant="primary" onClick={resolve} disabled={busy}>{busy ? "Resolving…" : "Accept higher authority"}</Button>
              {error && <p role="alert" className="text-caption text-danger">{error}</p>}
            </>
          ) : (
            <p className="text-caption text-muted">Resolving conflicts requires the engineer, reliability or admin role.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
