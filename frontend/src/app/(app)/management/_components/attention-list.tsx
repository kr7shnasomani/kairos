import Link from "next/link";
import { ListSkeleton } from "@/components/skeleton";
import { fmtRelTime } from "@/lib/format";
import { label } from "@/lib/labels";
import { staggerDelay } from "@/lib/motion";
import type { ComplianceDashboard, SlaReport } from "@/lib/types";

const CAP = 8;

interface Row {
  key: string;
  tone: "danger" | "caution";
  title: string;
  asset: string | null;
  since: string | null;
  href: string;
}

/** Spec §5 ranking: overdue conflicts → overdue quarantine → critical gaps.
 *  Capped at CAP rows; "View all" points at the dominant overdue source. */
function rank(sla: SlaReport | null, compliance: ComplianceDashboard | null): { rows: Row[]; total: number; viewAllHref: string | null } {
  const conflicts = (sla?.overdue_conflicts ?? []).map((c): Row => ({
    key: `conflict-${c.conflict_id}`,
    tone: "danger",
    title: `Overdue conflict · ${label(c.track)}`,
    asset: c.asset_id,
    since: c.sla_deadline,
    href: "/governance/conflicts",
  }));
  const quarantine = (sla?.overdue_quarantine_items ?? []).map((q): Row => ({
    key: `quarantine-${q.item_id}`,
    tone: "danger",
    // "Overdue" is factual, not decoration: this list is `sla.overdue_quarantine_items`, and being
    // past SLA is the only reason the row is under "Needs attention" at all. Matches the sibling
    // conflict row's `·` separator so the two read as one queue.
    //
    // Deliberately NOT `content ?? input_type`: `SLAService` selects only
    // `item_id, asset_id, input_type, sla_due_at`, so `content` is always undefined — and were it
    // ever added to that select, `elicitation_response` rows store a JSON array string, so the
    // list would render raw `[{"answer": …}]`.
    title: `Overdue quarantine · ${label(q.input_type)}`,
    asset: q.asset_id,
    since: q.sla_due_at,
    href: "/governance/quarantine",
  }));
  const critical = compliance?.total_gaps.critical ?? 0;
  const gaps: Row[] = critical > 0
    ? [{ key: "critical-gaps", tone: "caution", title: `${critical} critical compliance gap${critical === 1 ? "" : "s"}`, asset: null, since: null, href: "/compliance" }]
    : [];
  const all = [...conflicts, ...quarantine, ...gaps];
  const viewAllHref = all.length > CAP
    ? (conflicts.length >= quarantine.length ? "/governance/conflicts" : "/governance/quarantine")
    : null;
  return { rows: all.slice(0, CAP), total: all.length, viewAllHref };
}

/** Ranked triage queue — severity dot, title, asset chip, age, deep link. */
export function AttentionList({
  sla,
  compliance,
  loading = false,
}: {
  sla: SlaReport | null;
  compliance: ComplianceDashboard | null;
  loading?: boolean;
}) {
  const { rows, total, viewAllHref } = rank(sla, compliance);
  return (
    <section data-testid="overview-needs-attention" className="min-w-0 rounded-xl border border-line bg-surface p-5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Needs attention</h2>
        {!loading && viewAllHref && (
          <Link href={viewAllHref} className="text-label font-medium text-accent hover:underline">View all {total}</Link>
        )}
      </div>
      {loading ? (
        <div className="mt-3"><ListSkeleton rows={4} /></div>
      ) : rows.length === 0 ? (
        <p className="mt-3 flex items-center gap-2 text-body text-verified">
          <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
          Nothing needs attention — all clear.
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-line/60">
          {rows.map((r, i) => (
            <li key={r.key} className="animate-[rise-in_250ms_ease-out]" style={staggerDelay(i)}>
              <Link
                href={r.href}
                className="group -mx-2 flex items-center gap-3 rounded-md px-2 py-2.5 text-body text-ink transition-colors hover:bg-canvas"
              >
                <span className={`size-2 shrink-0 rounded-full ${r.tone === "danger" ? "bg-danger" : "bg-caution"}`} aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate" title={r.title}>{r.title}</span>
                {r.asset && <span className="shrink-0 rounded-md border border-line bg-surface-2 px-1.5 py-0.5 text-label text-muted">{r.asset}</span>}
                {r.since && <time className="tabular shrink-0 text-label text-muted">{fmtRelTime(r.since)}</time>}
                <span className="shrink-0 text-label text-muted transition-colors group-hover:text-accent" aria-hidden="true">›</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
