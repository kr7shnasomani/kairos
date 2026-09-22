import Link from "next/link";
import type { VaultDocument, AssetSummary, OperationalEvent } from "@/lib/types";
import { AuthorityBadge, StatusBadge, Truncate } from "@/components/ui";
import { plural } from "@/lib/labels";
import { triggerLabel, relativeTime } from "@/lib/utils";

export const FAILURE_TYPES = new Set(["work_order_created", "recurring_failure_detected", "alarm_acknowledged", "equipment_tag_out"]);

export interface ClassGroup {
  equipment_class: string;
  assets: AssetSummary[];
  documents: VaultDocument[];
  events: OperationalEvent[];
}

export function ClassSection({ group }: { group: ClassGroup }) {
  const failures = group.events
    .filter((e) => FAILURE_TYPES.has(e.event_type))
    .sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at));
  const revisions = group.documents.filter((document) => document.version_chain).length;
  const byType = new Map<string, VaultDocument[]>();
  for (const d of group.documents) {
    const list = byType.get(d.document_type) ?? [];
    list.push(d);
    byType.set(d.document_type, list);
  }
  const slug = group.equipment_class.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  const latest = failures[0];

  return (
    <section data-testid={`project-class-${slug}`} className="overflow-hidden border border-line bg-surface">
      <div className="p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-label font-semibold uppercase tracking-[0.1em] text-muted">{triggerLabel(group.equipment_class)}</p>
            <h2 className="mt-1 text-subtitle font-semibold text-ink">Equipment procurement record</h2>
          </div>
          {failures.length > 0 ? <StatusBadge tone="caution">{plural(failures.length, "signal")}</StatusBadge> : <StatusBadge tone="verified">Current</StatusBadge>}
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-caption text-muted">
          <span><b className="tabular text-ink">{group.assets.length}</b> assets</span>
          <span><b className="tabular text-ink">{group.documents.length}</b> documents</span>
          <span><b className="tabular text-ink">{revisions}</b> {revisions === 1 ? "revision" : "revisions"}</span>
        </div>
        {group.assets.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Linked assets">
            {group.assets.map((asset) => <span key={asset.asset_id} className="tabular border border-line bg-surface-2 px-2.5 py-1 text-label font-medium text-ink">{asset.asset_id}</span>)}
          </div>
        )}
      </div>

      <div className="grid border-t border-line xl:grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)]">
      <div className="space-y-4 p-4 sm:p-5 xl:border-r xl:border-line">
        <p className="text-label font-bold uppercase tracking-[0.1em] text-muted">Linked evidence</p>
        {byType.size === 0 && <p className="text-caption text-muted">No linked documents for this class.</p>}
        {Array.from(byType.entries()).map(([type, docs]) => (
          <div key={type}>
            <p className="mb-1.5 text-label font-semibold text-muted">{triggerLabel(type)}</p>
            <ul className="divide-y divide-line rounded-lg border border-line">
              {docs.map((d) => (
                <li key={d.document_id} className="flex flex-wrap items-center gap-2 px-3 py-2.5 text-caption">
                  <Link data-testid="evidence-id" href={`/documents/${d.document_id}`} className="tabular font-medium text-link hover:underline">
                    {d.document_id}
                  </Link>
                  <Truncate text={`${d.file_name} · ${d.source_system}`} className="min-w-0 flex-1 text-ink" />
                  <AuthorityBadge level={d.authority_level} />
                  {d.version_chain
                    ? <StatusBadge tone="info" dot={false}>rev</StatusBadge>
                    : null}
                  {d.status === "superseded"
                    ? <StatusBadge tone="caution" dot={false}>superseded</StatusBadge>
                    : null}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="bg-surface-2/40 p-4 sm:p-5">
        <p className="text-label font-bold uppercase tracking-[0.1em] text-muted">Maintenance history</p>
        {latest ? (
          <>
            <div className="mt-3 rounded-lg border border-[color-mix(in_srgb,var(--caution)_30%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_7%,var(--surface))] p-3">
              <p className="text-label font-semibold uppercase tracking-[0.08em] text-caution">Latest signal</p>
              <p className="mt-1 text-caption font-semibold text-ink">{triggerLabel(latest.event_type)}</p>
              <p className="tabular mt-1 text-label text-muted">{latest.asset_id} · {relativeTime(latest.occurred_at)}</p>
            </div>
            <ul className="mt-3 divide-y divide-line">
            {failures.slice(0, 8).map((e) => (
              <li key={e.event_id} className="flex flex-wrap items-center gap-2 py-2.5 text-caption">
                <span className="tabular text-ink">{e.asset_id}</span>
                <span className="text-ink">{triggerLabel(e.event_type)}</span>
                {typeof e.payload?.failure_code === "string" && (
                  <span className="text-muted">{e.payload.failure_code as string}</span>
                )}
                <span className="tabular ml-auto text-label text-muted">{relativeTime(e.occurred_at)}</span>
              </li>
            ))}
            </ul>
          </>
        ) : <p className="mt-3 text-caption text-muted">No failure or maintenance signals recorded.</p>}
      </div>
      </div>
    </section>
  );
}
