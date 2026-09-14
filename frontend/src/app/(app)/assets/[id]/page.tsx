// Asset detail — identity, stats, aliases, and knowledge graph for one canonical asset.
import Link from "next/link";
import { notFound } from "next/navigation";
import { getAssetDetail } from "@/lib/api";
import { AuthorityBadge, SourceChip, StatusBadge, PageHeader } from "@/components/ui";
// React Flow must not SSR — imported from the client-only lazy module.
import { KnowledgeGraph } from "@/components/lazy";
import { AssetSearch } from "./asset-search";
import { HierarchyPanel } from "./hierarchy-panel";

const VERIF_TONE = { verified: "verified", unverified: "caution", disputed: "danger" } as const;

export default async function AssetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { data: a } = await getAssetDetail(id);
  if (!a) notFound();

  const stats = [
    { label: "Open work orders", value: a.open_work_orders ?? "—" },
    { label: "Compliance gaps", value: a.compliance_gaps ?? "—" },
    { label: "Last inspection", value: a.last_inspection ?? "—" },
  ];

  return (
    <div data-testid="asset-detail-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/assets" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Assets
      </Link>

      <div data-testid="asset-summary" className="mt-4 overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
        <PageHeader
          compact
          className="px-4 py-5 sm:px-5"
          eyebrow={a.asset_id}
          title={a.name}
          lede={<>{a.equipment_class.replaceAll("_", " ")}{a.parent && <> · Parent {a.parent}</>}</>}
          actions={
            <>
              <span className="inline-flex h-[22px] items-center gap-1.5 rounded-full bg-surface-2 px-2 text-label font-semibold" style={{ color: a.criticalityColor }}>
                <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
                {a.criticalityLabel}
              </span>
            </>
          }
        />
        <div className="divide-y divide-line border-t border-line sm:grid sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          {stats.map((s) => (
            <div key={s.label} className="px-4 py-3.5 sm:px-5">
              <p className="text-micro font-semibold uppercase tracking-[0.1em] text-muted">{s.label}</p>
              <p className="tabular mt-1.5 text-title font-semibold leading-none text-ink">{s.value}</p>
            </div>
          ))}
        </div>
      </div>

      <div data-testid="asset-detail-columns" className="fluid-tile-pair mt-6">
        <section className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-4 sm:px-5">
            <div>
              <h2 className="text-sm font-semibold text-ink">Knowledge</h2>
              <p className="mt-0.5 text-caption text-muted">Operational facts linked to this asset — authority and verification status shown per fact.</p>
            </div>
            <span className="tabular text-label font-semibold text-muted">{a.knowledge.length} facts</span>
          </div>
          <div className="divide-y divide-line">
          {a.knowledge.length === 0 && (
            <p className="px-4 py-10 text-center text-body text-muted sm:px-5">
              No knowledge edges recorded for this asset yet.
            </p>
          )}
          {a.knowledge.map((k, i) => (
            <article key={`${k.source_doc}-${i}`} className="px-4 py-4 transition-colors hover:bg-surface-2 sm:px-5">
              <p className="max-w-3xl text-body leading-relaxed text-ink">{k.claim}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <AuthorityBadge level={k.authority_level} />
                <StatusBadge tone={VERIF_TONE[k.verification]}>{k.verification}</StatusBadge>
                <SourceChip quarantine={k.verification !== "verified"}>{k.source_doc}</SourceChip>
              </div>
            </article>
          ))}
          </div>
        </section>

        <aside className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
          <div className="border-b border-line px-4 py-4 sm:px-5">
            <h2 className="text-sm font-semibold text-ink">Asset identity</h2>
            <p className="mt-0.5 text-caption text-muted">Canonical master-data record.</p>
          </div>
          <dl className="divide-y divide-line px-4 sm:px-5">
            <div className="py-3.5">
              <dt className="text-label text-muted">Asset ID</dt>
              <dd className="tabular mt-1 text-caption font-semibold text-accent">{a.asset_id}</dd>
            </div>
            <div className="py-3.5">
              <dt className="text-label text-muted">Equipment class</dt>
              <dd className="mt-1 text-caption font-medium capitalize text-ink">{a.equipment_class.replaceAll("_", " ")}</dd>
            </div>
            <div className="py-3.5">
              <dt className="text-label text-muted">Parent asset</dt>
              <dd className="tabular mt-1 text-caption font-medium text-ink">{a.parent ?? "—"}</dd>
            </div>
            <div className="py-3.5">
              <dt className="text-label text-muted">Tag aliases</dt>
              <dd className="mt-2 flex flex-wrap gap-2">
                {a.aliases.length === 0 && <span className="text-caption text-muted">No aliases recorded</span>}
                {a.aliases.map((al) => (
                  <span key={al} className="tabular rounded-md border border-line bg-surface-2 px-2 py-1 text-caption text-muted">{al}</span>
                ))}
              </dd>
            </div>
          </dl>
        </aside>
      </div>

      <div className="fluid-tile-pair mt-6">
        <AssetSearch assetId={a.asset_id} />
        <HierarchyPanel assetId={a.asset_id} />
      </div>

      <section className="mt-6 overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-4 sm:px-5">
          <div>
            <h2 className="text-sm font-semibold text-ink">Knowledge graph</h2>
            <p className="mt-0.5 text-caption text-muted">Relationships connected to this asset.</p>
          </div>
          <Link
            href={`/graph?asset=${a.asset_id}`}
            className="shrink-0 text-caption font-semibold text-accent hover:underline focus-visible:outline-2 focus-visible:outline-accent"
          >
            Open full graph →
          </Link>
        </div>
        <div className="p-3 sm:p-4">
          <KnowledgeGraph assetId={a.asset_id} height={340} />
        </div>
      </section>
    </div>
  );
}
