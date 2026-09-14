"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { AssetSummary } from "@/lib/types";
import { label } from "@/lib/labels";
import { criticalityMeta } from "@/lib/utils";
import { DataTable, EmptyState, type TableColumn } from "@/components/ui";

type CriticalityFilter = "all" | "safety" | "critical" | "non-critical";

/** AssetSummary re-mapped so it satisfies DataTable's Record constraint. */
type AssetRow = Pick<AssetSummary, keyof AssetSummary>;

function matchesCriticality(value: string, filter: CriticalityFilter) {
  if (filter === "all") return true;
  if (filter === "safety") return value === "safety_critical" || value === "high";
  if (filter === "critical") return value === "critical" || value === "medium";
  return value === "non_critical" || value === "low";
}

const CRIT_RANK: Record<string, number> = { safety_critical: 0, high: 0, critical: 1, medium: 1, non_critical: 2, low: 2 };

const COLUMNS: TableColumn<AssetRow>[] = [
  { key: "asset_id", label: "Asset", sortable: true, render: (r) => <span className="tabular whitespace-nowrap font-semibold text-link">{r.asset_id}</span> },
  { key: "name", label: "Name", sortable: true, className: "w-[30%]", render: (r) => <span className="block truncate font-medium text-ink">{r.name}</span> },
  { key: "equipment_class", label: "Equipment class", sortable: true, render: (r) => <span className="block truncate text-caption text-muted">{label(r.equipment_class)}</span> },
  {
    key: "criticality", label: "Criticality", sortValue: (r) => CRIT_RANK[r.criticality] ?? 9,
    render: (r) => {
      const meta = criticalityMeta(r.criticality);
      return (
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-label font-semibold" style={{ color: meta.color }}>
          <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
          {meta.label}
        </span>
      );
    },
  },
  // Issue counts from `GET /assets/` (D6). Zero stays muted so the rows that need attention stand
  // out; a gap is a compliance finding, so it takes the danger tone rather than the accent.
  {
    key: "open_work_orders_count", label: "Open WOs", align: "right", sortable: true,
    render: (r) => <span className={`tabular ${r.open_work_orders_count ? "font-semibold text-ink" : "text-muted"}`}>{r.open_work_orders_count}</span>,
  },
  {
    key: "compliance_gap_count", label: "Compliance gaps", align: "right", sortable: true,
    render: (r) => <span className={`tabular ${r.compliance_gap_count ? "font-semibold text-danger" : "text-muted"}`}>{r.compliance_gap_count}</span>,
  },
];

export function AssetRegistry({ assets }: { assets: AssetSummary[] }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [equipmentClass, setEquipmentClass] = useState("all");
  const [criticality, setCriticality] = useState<CriticalityFilter>("all");

  const equipmentClasses = useMemo(
    () => [...new Set(assets.map((asset) => asset.equipment_class).filter(Boolean))].sort(),
    [assets],
  );
  const rows = useMemo<AssetRow[]>(() => {
    const needle = query.trim().toLowerCase();
    return assets.filter((asset) => {
      const searchable = [asset.asset_id, asset.tag_number, asset.name, asset.equipment_class, asset.site_id]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return (!needle || searchable.includes(needle))
        && (equipmentClass === "all" || asset.equipment_class === equipmentClass)
        && matchesCriticality(asset.criticality, criticality);
    });
  }, [assets, criticality, equipmentClass, query]);

  const hasFilters = Boolean(query || equipmentClass !== "all" || criticality !== "all");

  return (
    <section data-testid="asset-registry" className="mt-4">
      <div data-testid="asset-filter-toolbar" className="mb-3 flex flex-wrap items-center gap-2">
        <label className="relative block min-w-0 flex-1 sm:max-w-[280px]">
          <span className="sr-only">Search assets</span>
          <svg className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></svg>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search asset, tag, class, or site…"
            className="h-9 w-full rounded-lg border border-line bg-page pl-9 pr-3 text-body outline-none transition-colors placeholder:text-muted focus:border-accent"
          />
        </label>
        <label>
          <span className="sr-only">Equipment class</span>
          <select value={equipmentClass} onChange={(event) => setEquipmentClass(event.target.value)} className="h-9 rounded-lg border border-line bg-page px-3 text-body text-ink outline-none focus:border-accent">
            <option value="all">All equipment classes</option>
            {equipmentClasses.map((value) => <option key={value} value={value}>{label(value)}</option>)}
          </select>
        </label>
        <label>
          <span className="sr-only">Criticality</span>
          <select value={criticality} onChange={(event) => setCriticality(event.target.value as CriticalityFilter)} className="h-9 rounded-lg border border-line bg-page px-3 text-body text-ink outline-none focus:border-accent">
            <option value="all">All criticality</option>
            <option value="safety">Safety-critical</option>
            <option value="critical">Critical</option>
            <option value="non-critical">Non-critical</option>
          </select>
        </label>
        {hasFilters && (
          <button type="button" onClick={() => { setQuery(""); setEquipmentClass("all"); setCriticality("all"); }} className="h-9 rounded-lg px-3 text-caption font-medium text-muted transition-colors hover:bg-surface-2 hover:text-ink">
            Clear
          </button>
        )}
        <p className="tabular ml-auto whitespace-nowrap text-caption font-medium text-muted">{rows.length} of {assets.length} assets</p>
      </div>

      <DataTable<AssetRow>
        key={`${query}:${equipmentClass}:${criticality}`}
        columns={COLUMNS}
        rows={rows}
        keyFn={(r) => r.asset_id}
        pageSize={25}
        onRowClick={(r) => router.push(`/assets/${r.asset_id}`)}
        emptyState={<EmptyState message={hasFilters ? "No assets match these filters." : "No assets bootstrapped"} />}
      />
    </section>
  );
}
