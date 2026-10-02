"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
import type { OperationalEvent } from "@/lib/types";
import { getEvents } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { getMe } from "@/lib/auth";
import { useRole, RESOLVE_ROLES, visibleTo } from "@/components/use-role";
import { DemoGate } from "@/components/demo-gate";
import { Button, DataTable, EmptyState, FilterTabs, PageHeader, StatusBadge, statusTone, type TableColumn } from "@/components/ui";
import { AXIS, ChartContainer, GRID, TONE_VAR, TOOLTIP } from "@/components/charts";
import { useReducedMotion } from "@/lib/motion";
import { relativeTime, triggerLabel } from "@/lib/utils";
import { label } from "@/lib/labels";
import { EmitPanel } from "./_components/emit-panel";

import { Icon } from "@/components/icon";
/** OperationalEvent re-mapped so it satisfies DataTable's Record constraint. */
type EventRow = Pick<OperationalEvent, keyof OperationalEvent>;

// Severity order, not alphabetical. Used for BOTH the column sort and the order
// priorities appear in the filter tabs and the chart legend, so a `low` event
// arriving first in the payload cannot reorder anything.
const PRIORITY_RANK: Record<string, number> = { critical: 0, high: 1, normal: 2, low: 3 };
const rankOf = (p: string) => PRIORITY_RANK[p] ?? 99;

/** statusTone() returns the full Tone union; TONE_VAR only carries the chart
 *  subset. `validation` has no chart colour, so it falls back to neutral.
 *  Colour comes from the VALUE, never from its index in the series — a `low`
 *  event arriving first in the payload must not render as danger red. */
const priorityFill = (priority: string) => {
  const tone = statusTone(priority);
  return tone === "validation" ? TONE_VAR.neutral : TONE_VAR[tone];
};
// A trend needs more than two observations; shorter series are discrete counts.
const MAX_POINTS_FOR_BARS = 2;

// ponytail: first known payload string wins; extend the key list if new event
// types grow their own summary field.
const SUMMARY_KEYS = ["alarm_description", "findings", "tag_out_reason", "description", "summary"] as const;
function describeEvent(e: EventRow): string {
  for (const key of SUMMARY_KEYS) {
    const v = e.payload?.[key];
    if (typeof v === "string" && v) return v;
  }
  return triggerLabel(e.event_type);
}

const COLUMNS: TableColumn<EventRow>[] = [
  {
    key: "occurred_at", label: "Occurred", sortValue: (r) => Date.parse(r.occurred_at),
    render: (r) => <span className="tabular whitespace-nowrap text-caption text-muted" title={r.occurred_at}>{relativeTime(r.occurred_at)}</span>,
  },
  {
    key: "priority", label: "Priority", sortValue: (r) => rankOf(r.priority),
    render: (r) => <StatusBadge tone={statusTone(r.priority)}>{label(r.priority)}</StatusBadge>,
  },
  {
    key: "event_type", label: "Type", sortValue: (r) => triggerLabel(r.event_type),
    render: (r) => <span className="whitespace-nowrap font-semibold text-ink">{triggerLabel(r.event_type)}</span>,
  },
  {
    key: "asset_id", label: "Asset",
    render: (r) => r.asset_id ? <Link href={`/assets/${encodeURIComponent(r.asset_id)}`} onClick={(event) => event.stopPropagation()} className="tabular text-caption font-medium text-link">{r.asset_id}</Link> : <span>—</span>,
  },
  {
    key: "description", label: "Description", className: "w-[38%]",
    render: (r) => <span className="block truncate text-muted" title={describeEvent(r)}>{describeEvent(r)}</span>,
  },
  {
    key: "acknowledged", label: "Status",
    render: (r) => <StatusBadge tone={r.acknowledged ? "verified" : "neutral"}>{r.acknowledged ? "acknowledged" : "pending"}</StatusBadge>,
  },
];

export default function EventsPage() {
  const router = useRouter();
  const role = useRole();
  const canEmit = visibleTo(RESOLVE_ROLES, role);
  const reduced = useReducedMotion();

  const [reload, setReload] = useState(0);
  // Spec §5: params unchanged — same { limit: 50 } call shape as before.
  const state = useFetch(() => getEvents({ limit: 50 }), [reload]);
  const loading = state.status === "loading";
  const hasData = state.status === "live";
  const events = useMemo<OperationalEvent[]>(() => (hasData ? state.data.items ?? [] : []), [state, hasData]);

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [siteId, setSiteId] = useState("SITE_001");
  const [userId, setUserId] = useState("dev-user");
  const [showEmitter, setShowEmitter] = useState(false);
  useEffect(() => { getMe().then((u) => { if (u) { setSiteId(u.site_id); setUserId(u.user_id); } }); }, []);

  const types = useMemo(() => Array.from(new Set(events.map((e) => e.event_type))), [events]);
  // Sorted by severity so the legend, the filter tabs and the chart series all
  // agree, whatever order the API happened to return rows in.
  const priorities = useMemo(
    () => Array.from(new Set(events.map((e) => e.priority))).sort((a, b) => rankOf(a) - rankOf(b)),
    [events],
  );
  const priorityCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of events) counts[e.priority] = (counts[e.priority] ?? 0) + 1;
    return counts;
  }, [events]);

  // Filter (type + priority tabs, free-text search) then default newest-first.
  const rows = useMemo<EventRow[]>(() => {
    const query = search.trim().toLowerCase();
    return events
      .filter((e) => {
        if (typeFilter !== "all" && e.event_type !== typeFilter) return false;
        if (priorityFilter !== "all" && e.priority !== priorityFilter) return false;
        if (!query) return true;
        return [e.event_id, e.asset_id ?? "", triggerLabel(e.event_type)].some((v) => v.toLowerCase().includes(query));
      })
      .sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at));
  }, [events, typeFilter, priorityFilter, search]);

  // Events/day × priority over the received window — follows the active filters.
  const trend = useMemo(() => {
    const byDay = new Map<string, Record<string, number>>();
    for (const e of rows) {
      const day = e.occurred_at.slice(0, 10);
      const bucket = byDay.get(day) ?? {};
      bucket[e.priority] = (bucket[e.priority] ?? 0) + 1;
      byDay.set(day, bucket);
    }
    return [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([day, counts]) => ({ day, ...counts }));
  }, [rows]);
  const showDiscreteBars = trend.length <= MAX_POINTS_FOR_BARS;

  const hasFilters = search !== "" || typeFilter !== "all" || priorityFilter !== "all";

  return (
    <div data-testid="events-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader
        eyebrow="Operate"
        title="Operational events"
        lede="Monitor the event sources that trigger proactive briefs and compound operational context."
        actions={canEmit && <DemoGate><Button variant="primary" className="h-11 sm:h-9" onClick={() => setShowEmitter((open) => !open)}>{showEmitter ? "Close emitter" : "Emit event"}</Button></DemoGate>}
      />

      <div className="mt-3 flex flex-wrap items-center gap-3 text-caption text-muted">
        <span className="tabular font-medium text-ink">{events.length} event{events.length !== 1 ? "s" : ""}</span>
        {/* A partial fetch must never present itself as the whole set. */}
        {state.status === "live" && state.data.total > events.length && (
          <span className="tabular">{events.length} of {state.data.total} loaded</span>
        )}
      </div>

      {canEmit && showEmitter && <EmitPanel siteId={siteId} userId={userId} onEmitted={() => setReload((r) => r + 1)} />}

      <section data-testid="events-filter-toolbar" className="mt-5 flex flex-wrap items-center gap-3">
        <FilterTabs
          tabs={[{ key: "all", label: "All priorities" }, ...priorities.map((p) => ({ key: p, label: label(p), count: priorityCounts[p] }))]}
          active={priorityFilter}
          onChange={setPriorityFilter}
        />
        <FilterTabs
          tabs={[{ key: "all", label: "All types" }, ...types.map((t) => ({ key: t, label: triggerLabel(t) }))]}
          active={typeFilter}
          onChange={setTypeFilter}
        />
        <label className="flex h-9 min-w-[220px] flex-1 items-center gap-2 rounded-lg border border-line bg-surface px-3 focus-within:border-accent sm:max-w-[280px]">
          <Icon name="magnifying-glass" size={16} className="shrink-0 text-muted" />
          <input type="search" aria-label="Search events" placeholder="Search event, asset, or ID" value={search} onChange={(e) => setSearch(e.target.value)} className="min-w-0 flex-1 bg-transparent text-body outline-none placeholder:text-muted" />
        </label>
      </section>

      <ChartContainer
        className="mt-4"
        title="Event volume"
        sub="Events per day by priority, last 50 events"
        height={160}
        loading={loading}
        empty={trend.length === 0 && "No events in window"}
        error={state.status === "error"}
        onRetry={state.status === "error" ? state.retry : undefined}
      >
        {showDiscreteBars ? (
          <BarChart data={trend} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="day" {...AXIS} tickFormatter={(d) => String(d).slice(5)} interval={0} />
            <YAxis {...AXIS} width={32} allowDecimals={false} />
            <Tooltip {...TOOLTIP} />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: "var(--muted)" }} />
            {priorities.map((p) => (
              <Bar key={p} dataKey={p} name={label(p)} fill={priorityFill(p)} isAnimationActive={!reduced} />
            ))}
          </BarChart>
        ) : (
          <LineChart data={trend} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="day" {...AXIS} tickFormatter={(d) => String(d).slice(5)} interval={0} />
            <YAxis {...AXIS} width={32} allowDecimals={false} />
            <Tooltip {...TOOLTIP} />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: "var(--muted)" }} />
            {priorities.map((p) => (
              <Line key={p} type="monotone" dataKey={p} name={label(p)} stroke={priorityFill(p)} strokeWidth={2} dot={false} isAnimationActive={!reduced} />
            ))}
          </LineChart>
        )}
      </ChartContainer>

      <section data-testid="events-table" className="mt-4">
        <p className="tabular mb-2 text-caption font-medium text-muted">{rows.length} of {events.length} events</p>
        {state.status === "error" ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-line bg-surface px-4 py-10 text-center">
            <p className="text-body text-muted">Could not load operational events.</p>
            <Button variant="primary" onClick={state.retry}>Retry</Button>
          </div>
        ) : (
          <DataTable<EventRow>
            key={`${typeFilter}:${priorityFilter}:${search}`}
            columns={COLUMNS}
            rows={rows}
            keyFn={(r) => r.event_id}
            pageSize={25}
            loading={loading}
            onRowClick={(r) => router.push(`/events/${r.event_id}`)}
            emptyState={<EmptyState message={hasFilters ? "No events match these filters." : canEmit ? "No events yet — emit one to see the flow end-to-end." : "No operational events recorded."} />}
          />
        )}
      </section>
    </div>
  );
}
