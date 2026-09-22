"use client";

import { useEffect, useMemo, useState } from "react";
import type { VaultDocument, AssetSummary, OperationalEvent } from "@/lib/types";
import { getDocuments, getAssets, getEvents } from "@/lib/api";
import { EmptyState, PageHeader } from "@/components/ui";
import { plural } from "@/lib/labels";
import { triggerLabel } from "@/lib/utils";
import { ClassSection, FAILURE_TYPES, type ClassGroup } from "./_components/class-section";

const UNCLASSIFIED = "Unclassified";

export default function ProjectsPage() {
  const [documents, setDocuments] = useState<VaultDocument[]>([]);
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [events, setEvents] = useState<OperationalEvent[]>([]);
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [active, setActive] = useState<string>("all");

  useEffect(() => {
    let alive = true;
    Promise.all([getDocuments(), getAssets(), getEvents({ limit: 100 })]).then(([d, a, e]) => {
      if (!alive) return;
      // Live-only is now enforced in the fetchers themselves: they throw rather than
      // returning a fixture, so a failure lands in .catch() below.
      setFailed(false);
      setDocuments(d.data.items);
      setAssets(a.data.items);
      setEvents(e.data.items);
    }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [reload]);

  // asset_id -> equipment_class, so documents and events can be bucketed by class.
  const classOf = useMemo(() => {
    const m = new Map<string, string>();
    for (const a of assets) m.set(a.asset_id, a.equipment_class);
    return m;
  }, [assets]);

  const groups = useMemo<ClassGroup[]>(() => {
    const by = new Map<string, ClassGroup>();
    const ensure = (cls: string) =>
      by.get(cls) ?? by.set(cls, { equipment_class: cls, assets: [], documents: [], events: [] }).get(cls)!;
    for (const a of assets) ensure(a.equipment_class).assets.push(a);
    for (const d of documents) {
      const cls = d.asset_links?.map((id) => classOf.get(id)).find(Boolean) ?? UNCLASSIFIED;
      ensure(cls).documents.push(d);
    }
    for (const ev of events) {
      const cls = (ev.asset_id && classOf.get(ev.asset_id)) || UNCLASSIFIED;
      ensure(cls).events.push(ev);
    }
    return Array.from(by.values()).sort((a, b) => b.documents.length - a.documents.length);
  }, [assets, documents, events, classOf]);

  const classNames = groups.map((g) => g.equipment_class);
  const visible = active === "all" ? groups : groups.filter((g) => g.equipment_class === active);
  const maintenanceSignals = events.filter((event) => FAILURE_TYPES.has(event.event_type)).length;
  const revisionCount = documents.filter((document) => document.version_chain).length;

  if (failed) {
    return (
      <div data-testid="projects-workspace" className="mx-auto max-w-[1400px]">
        <div className="mt-6 rounded-xl border border-line bg-surface p-8 text-center">
          <p className="text-body font-medium text-ink">Couldn&apos;t load the engineering portfolio.</p>
          <p className="mt-1 text-caption text-muted">Live data is unavailable right now.</p>
          <button type="button" onClick={() => setReload((r) => r + 1)} className="mt-4 inline-flex min-h-11 items-center rounded-lg border border-line bg-surface-2 px-4 text-caption font-medium text-ink transition-colors hover:bg-canvas">
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="projects-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader eyebrow="Project &amp; procurement" title="Engineering portfolio" lede="Documents, revisions, and failure/maintenance history organised by equipment class: the record a procurement officer needs when evaluating a replacement or a vendor." />

      <div data-testid="projects-portfolio-pulse" className="mt-6 grid overflow-hidden rounded-xl border border-line bg-surface shadow-sm sm:grid-cols-2 lg:grid-cols-[minmax(0,1.25fr)_repeat(3,minmax(130px,0.55fr))]">
        <div className="relative bg-[linear-gradient(120deg,color-mix(in_srgb,var(--info)_7%,var(--surface)),var(--surface))] px-5 py-5 sm:col-span-2 lg:col-span-1">
          <span aria-hidden="true" className="absolute bottom-3 left-2 top-3 w-[3px] bg-info" />
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-label font-semibold uppercase tracking-[0.1em] text-muted">Portfolio coverage</p>
          </div>
          <p className="tabular mt-1 text-title font-semibold text-ink">{classNames.length} equipment classes</p>
          <p className="mt-1 text-label text-muted">{plural(revisionCount, "retained revision")} across the procurement record</p>
        </div>
        <PortfolioMetric value={assets.length} label="assets" className="sm:border-r lg:border-l" />
        <PortfolioMetric value={documents.length} label="documents" />
        <PortfolioMetric value={maintenanceSignals} label="maintenance signals" tone={maintenanceSignals > 0 ? "caution" : undefined} className="sm:col-span-2 lg:col-span-1 lg:border-l" />
      </div>

      <div data-testid="projects-portfolio" className="mt-6 grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
        {classNames.length > 0 && (
          <aside data-testid="projects-class-navigation" className="rounded-xl border border-line bg-surface p-2 shadow-sm lg:sticky lg:top-6">
            <p className="px-2 pb-2 pt-1 text-label font-semibold uppercase tracking-[0.1em] text-muted">Equipment classes</p>
            <div className="flex flex-wrap gap-1 lg:flex-col" role="group" aria-label="Equipment classes">
              <ClassButton label="All classes" count={groups.length} active={active === "all"} onClick={() => setActive("all")} />
              {groups.map((group) => (
                <ClassButton key={group.equipment_class} label={triggerLabel(group.equipment_class)} count={group.assets.length} active={active === group.equipment_class} onClick={() => setActive(group.equipment_class)} />
              ))}
            </div>
          </aside>
        )}

        <div className="space-y-4">
        {visible.length === 0 && <EmptyState message="No registry data yet — ingest documents and assets to populate." action={{ label: "Ingest a document", href: "/documents/ingest" }} />}
        {visible.map((g) => <ClassSection key={g.equipment_class} group={g} />)}
        </div>
      </div>
    </div>
  );
}
function PortfolioMetric({ value, label, tone, className = "" }: { value: number; label: string; tone?: "caution"; className?: string }) {
  return (
    <div className={`border-t border-line px-5 py-4 lg:border-t-0 ${className}`}>
      <p className={`tabular text-title font-semibold ${tone === "caution" ? "text-caution" : "text-ink"}`}>{value}</p>
      <p className="mt-1 text-label font-medium uppercase tracking-[0.08em] text-muted">{label}</p>
    </div>
  );
}

function ClassButton({ label, count, active, onClick }: { label: string; count: number; active: boolean; onClick: () => void }) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick} className={`flex min-h-11 items-center justify-between gap-3 rounded-lg px-3 text-left text-caption font-semibold transition-colors ${active ? "bg-surface-2 text-ink" : "text-muted hover:bg-surface-2 hover:text-ink"}`}>
      <span>{label}</span><span className="tabular text-label text-muted">{count}</span>
    </button>
  );
}
