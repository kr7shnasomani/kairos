import Link from "next/link";
import type { Conflict } from "@/lib/types";
import { relativeTime, slaCountdown } from "@/lib/utils";
import { StatusBadge, type TableColumn } from "@/components/ui";

/** Conflict re-mapped so it satisfies DataTable's Record constraint. */
export type ConflictRow = Pick<Conflict, keyof Conflict>;

const SEV_TONE: Record<string, "danger" | "caution" | "verified" | "neutral"> = {
  critical: "danger",
  major: "caution",
  minor: "verified",
};

/** The two conflict producers emit different source shapes, and the column has to read both.
 *
 *  `services/graph.py detect_conflict` — 93 of 94 live rows — emits only `edge_id`,
 *  `document_id`, `authority_level` and `confidence`. It fires whenever two edges share a
 *  `relationship_type` from different documents, WITHOUT comparing what they assert, so there is
 *  no contradicting value to show and none is stored. Reading `source.value` on those rows
 *  produced the literal "— vs —" on every one.
 *
 *  The seeded engineering conflict (HE-301 max operating pressure, 18.5 bar against 16.2 bar)
 *  does carry `value` plus a human-readable `source`. That row is the one this column was built
 *  for and it must keep rendering exactly as before.
 *
 *  So: show the disagreement when the data actually holds one, and otherwise name the two
 *  sources — real provenance rather than an em dash. "vs" is reserved for a genuine
 *  contradiction; co-documentation gets a neutral separator, because calling it "vs" asserts a
 *  disagreement nobody detected. */
function contradiction(c: ConflictRow): { text: string; conflicting: boolean } | null {
  const a = c.source_a;
  const b = c.source_b;
  const aVal = a?.value;
  const bVal = b?.value;
  if (aVal != null && bVal != null) {
    return { text: `${String(aVal)} vs ${String(bVal)}`, conflicting: true };
  }

  const label = (s: typeof a): string | null => {
    if (!s) return null;
    const name = typeof s.source === "string" ? s.source : s.document_id;
    if (!name) return null;
    const auth = s.authority_level;
    return typeof auth === "number" ? `${name} (L${auth})` : String(name);
  };
  const parts = [label(a), label(b)].filter((x): x is string => !!x);
  if (parts.length === 0) return null;
  return { text: parts.join(" · "), conflicting: false };
}

function SlaChip({ c, nowMs }: { c: ConflictRow; nowMs: number }) {
  if (c.status === "resolved" || !c.sla_due_at) return <span className="text-muted">—</span>;
  if (c.is_overdue) return <span className="tabular whitespace-nowrap text-label font-semibold text-danger">SLA overdue</span>;
  const { label, tone } = slaCountdown(c.sla_due_at, nowMs);
  return <span className={`tabular whitespace-nowrap text-label font-semibold ${tone}`}>{label}</span>;
}

export function buildColumns(nowMs: number, busy: string | null, onResolve: (c: ConflictRow) => void): TableColumn<ConflictRow>[] {
  return [
    { key: "conflict_id", label: "Conflict", sortable: true, render: (r) => <Link href={`/governance/conflicts/${r.conflict_id}`} className="tabular whitespace-nowrap font-semibold text-accent hover:underline">{r.conflict_id}</Link> },
    { key: "track", label: "Track", sortable: true, render: (r) => <StatusBadge tone={r.track === "engineering" ? "danger" : "info"} dot={false}>{r.track}</StatusBadge> },
    { key: "severity", label: "Severity", sortable: true, render: (r) => <StatusBadge tone={SEV_TONE[r.severity] ?? "neutral"}>{r.severity}</StatusBadge> },
    {
      key: "parameter", label: "Parameter & sources", className: "w-[38%]",
      render: (r) => {
        const detail = contradiction(r);
        return (
          <span className="block min-w-0">
            <span className="block truncate font-medium text-ink">{r.parameter.replace(/_/g, " ")}</span>
            {detail ? (
              <span
                className="tabular block truncate text-label text-muted"
                title={detail.text}
              >
                {detail.text}
              </span>
            ) : (
              <span className="block truncate text-label text-muted">Sources not recorded</span>
            )}
          </span>
        );
      },
    },
    {
      key: "asset_id", label: "Asset",
      render: (r) => r.asset_id
        ? <Link href={`/assets/${r.asset_id}`} className="tabular whitespace-nowrap text-caption font-medium text-accent hover:underline">{r.asset_id}</Link>
        : <span className="text-muted">—</span>,
    },
    {
      key: "created_at", label: "Age", sortValue: (r) => Date.parse(r.created_at),
      render: (r) => <span className="tabular whitespace-nowrap text-caption text-muted" title={r.created_at}>{relativeTime(r.created_at)}</span>,
    },
    {
      key: "sla", label: "SLA",
      sortValue: (r) => (r.status !== "resolved" && r.is_overdue ? 0 : r.sla_due_at ? Date.parse(r.sla_due_at) : Number.MAX_SAFE_INTEGER),
      render: (r) => <SlaChip c={r} nowMs={nowMs} />,
    },
    {
      key: "resolution", label: "Resolution",
      render: (r) =>
        r.status === "resolved" ? (
          <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-caption font-semibold text-verified">
            <span className="size-1.5 rounded-full bg-verified" aria-hidden="true" />Resolved
          </span>
        ) : r.track === "engineering" ? (
          <Link href="/governance/moc" className="whitespace-nowrap text-caption font-semibold text-accent hover:underline">MoC required →</Link>
        ) : (
          <button
            onClick={() => onResolve(r)}
            disabled={busy === r.conflict_id}
            className="inline-flex h-8 items-center whitespace-nowrap rounded-lg bg-accent px-3 text-caption font-semibold text-on-accent transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy === r.conflict_id ? "Resolving…" : "Resolve"}
          </button>
        ),
    },
  ];
}
