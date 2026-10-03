"use client";

import { useState } from "react";
import type { Brief, BriefPriority, BriefsResponse } from "@/lib/types";
import { cn, priorityMeta, relativeTime } from "@/lib/utils";
import { BriefCard } from "./brief-card";
import { Icon } from "./icon";
import { EmptyState, FilterTabs } from "./ui";

// PTW-critical first, then by priority order per EEMUA-191.
const PRIORITY_ORDER: BriefPriority[] = ["critical", "high", "normal", "medium", "low"];

type FilterKey = "all" | "unacknowledged" | "critical";

function GovernorBanner({ response }: { response: BriefsResponse }) {
  const gov = response.governor_state;
  const pct = Math.min(100, Math.round((gov.push_count_last_hour / gov.ceiling) * 100));
  const atCeiling = gov.state === "suppressed";
  const held = response.suppressed_held ?? [];

  if (!atCeiling && response.suppressed_count === 0) {
    return null;
  }

  const queued = response.suppressed_count;
  return (
    <section aria-label="Brief delivery governor" className="rounded-xl border border-line bg-surface">
      <div className="flex items-center gap-5 px-4 py-3.5">
        <div className="min-w-0 flex-1">
          <p className="text-body font-semibold text-ink">
            {queued > 0
              ? `${queued} routine brief${queued !== 1 ? "s" : ""} queued`
              : "Delivery paused until the hour rolls over"}
          </p>
          <p className="mt-0.5 text-caption text-pretty text-muted">
            The EEMUA 191 governor sends each operator at most {gov.ceiling} pushes an hour, so routine briefs wait their
            turn. Permits and safety briefs are never held.
            {response.next_delivery_allowed_at && <> Next delivery {relativeTime(response.next_delivery_allowed_at)}.</>}
          </p>
        </div>
        <div className="w-28 shrink-0 text-right">
          <p className={cn("tabular text-title font-semibold", atCeiling ? "text-danger" : "text-ink")}>
            {gov.push_count_last_hour}<span className="text-body font-normal text-muted">/{gov.ceiling}</span>
          </p>
          <p className="text-micro uppercase tracking-[0.1em] text-muted">pushes this hour</p>
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-line">
            <div className={cn("h-full", atCeiling ? "bg-danger" : "bg-accent")} style={{ width: `${pct}%` }} />
          </div>
        </div>
      </div>

      {/* What is waiting, not just how many: a bare count cannot answer "does it concern my asset", which
          decides whether to act. Closed by default so a long queue never pushes the real briefs off screen. */}
      {held.length > 0 && (
        <details className="group border-t border-line">
          <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-4 text-caption font-medium text-muted transition-colors hover:text-ink">
            <Icon name="caret-right" size={12} className="transition-transform group-open:rotate-90" />
            Show the queued briefs
          </summary>
          <ul className="space-y-1.5 px-4 pb-3">
            {held.map((b) => (
              <li key={b.brief_id} className="flex items-baseline justify-between gap-3 text-caption">
                <span className="min-w-0 flex-1 truncate text-muted">
                  <span className="font-medium text-ink">{b.headline}</span>
                  {b.asset_id ? <>, {b.asset_id}</> : null}
                </span>
                <span className="tabular shrink-0 text-muted">{relativeTime(b.delivered_at)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export function BriefInbox({ response }: { response: BriefsResponse }) {
  const { briefs } = response;
  const [filter, setFilter] = useState<FilterKey>("all");
  const criticalCount = briefs.filter((brief) => brief.priority === "critical").length;

  const filterTabs = [
    { key: "all" as FilterKey, label: "All", count: briefs.length },
    { key: "unacknowledged" as FilterKey, label: "Unacknowledged", count: briefs.filter((b) => !b.acknowledged_at).length },
    { key: "critical" as FilterKey, label: "Critical", count: briefs.filter((b) => b.priority === "critical").length },
  ].filter((t) => t.key === "all" || t.count > 0);

  const filtered =
    filter === "unacknowledged" ? briefs.filter((b) => !b.acknowledged_at) :
    filter === "critical" ? briefs.filter((b) => b.priority === "critical") :
    briefs;

  const groups = PRIORITY_ORDER.filter((p) => filtered.some((b) => b.priority === p));

  // PTW briefs surface first within critical
  function sortGroup(group: Brief[]): Brief[] {
    return [...group].sort((a, b) => {
      if (a.requires_countersignature && !b.requires_countersignature) return -1;
      if (!a.requires_countersignature && b.requires_countersignature) return 1;
      return 0;
    });
  }

  return (
    <div className="space-y-4">
      <div data-testid="brief-toolbar" className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-3 md:flex-row md:items-center md:justify-between">
        <FilterTabs
          tabs={filterTabs}
          active={filter}
          onChange={(k) => setFilter(k as FilterKey)}
        />
        <div className="flex flex-wrap items-center gap-2 text-caption">
          <span className={cn(
            "inline-flex min-h-8 items-center gap-1.5 px-3 font-medium",
            response.total_pending > 0
              ? "bg-[color-mix(in_srgb,var(--caution)_10%,transparent)] text-caution"
              : "bg-[color-mix(in_srgb,var(--verified)_9%,transparent)] text-verified",
          )}>
            <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
            <span className="tabular">{response.total_pending} pending</span>
          </span>
          {criticalCount > 0 && (
            <span className="inline-flex min-h-8 items-center gap-1.5 bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] px-3 font-medium text-danger">
              <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
              <span className="tabular">{criticalCount} critical</span>
            </span>
          )}
          <span className={cn(
            "inline-flex min-h-8 items-center gap-1.5 px-3 font-medium",
            response.governor_state.state === "suppressed" || response.suppressed_count > 0
              ? "bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] text-danger"
              : "bg-[color-mix(in_srgb,var(--verified)_9%,transparent)] text-verified",
          )}>
            <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
            <span className="tabular">{response.governor_state.push_count_last_hour}/{response.governor_state.ceiling} governor</span>
          </span>
        </div>
      </div>

      <GovernorBanner response={response} />

      <div className="flex flex-col gap-4">
        {groups.length === 0 && (
          <EmptyState message="No briefs in this view." />
        )}
        {groups.map((p) => {
          const group = sortGroup(filtered.filter((b) => b.priority === p));
          return (
            <section key={p} aria-label={`${priorityMeta(p).label} briefs`}>
              <div className="mb-2 flex items-center gap-2 px-0.5">
                <span className="size-1.5 rounded-full" style={{ background: priorityMeta(p).color }} aria-hidden="true" />
                <h2 className="text-label font-bold uppercase tracking-[0.1em] text-muted">
                  {priorityMeta(p).label}
                </h2>
                <span className="tabular text-label text-muted">{group.length}</span>
              </div>
              <div className="flex flex-col gap-3">
                {group.map((b) => <BriefCard key={b.brief_id} brief={b} />)}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
