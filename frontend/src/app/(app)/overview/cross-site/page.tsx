"use client";

import Link from "next/link";
import { EmptyState, PageHeader, StatusBadge } from "@/components/ui";
import { Icon } from "@/components/icon";
import { getCrossSitePatterns } from "@/lib/api";
import { label, plural } from "@/lib/labels";
import type { CrossSitePattern } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";
import { relativeTime } from "@/lib/utils";

// A pattern is the same failure family on the same equipment class at more than one site, or
// recurring at one site while a sister site runs that class. The server sends counts and codes
// only, so nothing personal crosses a site boundary and there is no free text to render.

function PatternCard({ pattern }: { pattern: CrossSitePattern }) {
  const shared = pattern.kind === "shared";
  return (
    <li data-testid="cross-site-pattern" className="rounded-xl border border-line bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-body font-semibold text-ink">
          {label(pattern.failure_family)} on {label(pattern.equipment_class)}
        </h2>
        <StatusBadge tone={shared ? "danger" : "caution"} dot={false}>
          {shared ? "Seen at more than one site" : "Advisory"}
        </StatusBadge>
      </div>
      <table className="mt-3 w-full text-body">
        <thead>
          <tr className="text-left text-label text-muted">
            <th scope="col" className="py-1 font-medium">Site</th>
            <th scope="col" className="py-1 text-right font-medium">Work orders</th>
            <th scope="col" className="py-1 text-right font-medium">Assets affected</th>
            <th scope="col" className="py-1 text-right font-medium">Last seen</th>
          </tr>
        </thead>
        <tbody>
          {pattern.sites.map((s) => (
            <tr key={s.site_id} className="border-t border-line">
              <td className="py-1.5 text-ink">{s.site_id}</td>
              <td className="py-1.5 text-right tabular text-ink">{s.events}</td>
              <td className="py-1.5 text-right tabular text-ink">
                {s.assets_affected} of {s.assets_in_class}
              </td>
              <td className="py-1.5 text-right text-muted">
                {s.last_seen ? relativeTime(s.last_seen) : "Not seen here"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </li>
  );
}

export default function CrossSiteAlertsPage() {
  const state = useFetch(() => getCrossSitePatterns(), []);

  return (
    <div data-testid="cross-site-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/overview" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <Icon name="caret-left" size={15} />
        Overview
      </Link>

      <PageHeader
        className="mt-4"
        title="Cross-Site Pattern Alerts"
        lede="Failure patterns that repeat on the same equipment class at more than one site, so a problem seen at one plant can warn the others. Only counts and failure codes cross a site boundary, never names or work order text."
      />

      {state.status === "loading" && (
        <div className="mt-6 h-64 animate-pulse rounded-xl border border-line bg-surface-2" />
      )}

      {state.status === "error" && (
        <div className="mt-6 flex flex-wrap items-center gap-3 rounded-xl border border-[color-mix(in_srgb,var(--danger)_30%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_5%,var(--surface))] p-4 text-body text-ink">
          <span>Couldn&apos;t load cross-site patterns.</span>
          <button onClick={state.retry} className="rounded-lg border border-line px-3 py-1.5 text-body hover:bg-surface-2">
            Retry
          </button>
        </div>
      )}

      {state.status === "live" && state.data.patterns.length === 0 && (
        <div data-testid="cross-site-empty" className="mt-6 rounded-xl border border-line bg-surface">
          <EmptyState
            message={
              state.data.sites.length < 2
                ? "Your account covers one site, so there is nothing to compare."
                : `No failure family has reached ${state.data.min_events} work orders on a shared equipment class in the last ${state.data.window_days} days.`
            }
          />
        </div>
      )}

      {state.status === "live" && state.data.patterns.length > 0 && (
        <>
          <p className="mt-6 text-caption text-muted">
            {plural(state.data.patterns.length, "pattern")} across {plural(state.data.sites.length, "site")} from work orders
            in the last {state.data.window_days} days. A pattern needs at least {state.data.min_events} work orders in one
            failure family at one site.
            {state.data.truncated ? " Only the newest work orders were counted." : ""}
          </p>
          <ul className="mt-3 grid gap-3 lg:grid-cols-2">
            {state.data.patterns.map((p) => (
              <PatternCard key={`${p.equipment_class}:${p.failure_family}`} pattern={p} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
