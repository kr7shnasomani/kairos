"use client";

// Management overview — KPI strip (deep-linked), 14-day event trend, ranked
// attention queue, live signals feed, system health. One useFetch drives
// every zone: loading skeletons → live/demo → error + retry.
import Link from "next/link";
import { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, ChartCard, GRID, TOOLTIP } from "@/components/charts";
import { MetricCard, PageHeader, StatusBadge } from "@/components/ui";
import type { Fetched } from "@/lib/api";
import { getComplianceDashboard, getConflicts, getEvents, getHealthDetailed, getQuarantine, getSlaReport } from "@/lib/api";
import { label } from "@/lib/labels";
import { useScrollReveal } from "@/lib/motion";
import type { ComplianceDashboard, OperationalEvent, SlaReport } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";
import { nowMs } from "@/lib/utils";
import { AttentionList } from "./_components/attention-list";
import { HealthStrip } from "./_components/health-strip";
import { SignalsFeed } from "./_components/signals-feed";

const DAY_MS = 86_400_000;
const TREND_DAYS = 14;

interface Overview {
  conflictsTotal: number | null;
  quarantineTotal: number | null;
  sla: SlaReport | null;
  compliance: ComplianceDashboard | null;
  events: OperationalEvent[];
}

/** The five core situational-awareness sources in parallel; demo when any fell back.
 *  System health is fetched separately (see ManagementPage) — it pings every cloud
 *  store (~2.5s) and must never block the core data or blank the page when a cloud
 *  ping spikes. */
async function fetchOverview(): Promise<Fetched<Overview>> {
  const [cr, qr, sr, dr, er] = await Promise.all([
    getConflicts(),
    getQuarantine(),
    getSlaReport(),
    getComplianceDashboard(),
    getEvents({ limit: 200 }),
  ]);
  return {
    data: {
      conflictsTotal: cr.data?.total ?? null,
      quarantineTotal: qr.data?.total ?? null,
      sla: sr.data,
      compliance: dr.data,
      events: er.data?.items ?? [],
    },
    source: "live",
  };
}

/** End of the trend window: now, unless the newest event is older than the whole window. Demo data
 *  keeps its in-story dates, so a window ending today was all empty days and read as "no activity". */
function trendEnd(events: OperationalEvent[]) {
  const now = nowMs();
  const newest = Math.max(...events.map((e) => Date.parse(e.occurred_at)).filter((t) => !Number.isNaN(t)));
  return Number.isFinite(newest) && now - newest > TREND_DAYS * DAY_MS ? newest : now;
}

/** Bucket events into daily counts for the TREND_DAYS days ending at `endMs`. */
function dailyCounts(events: OperationalEvent[], endMs: number) {
  const start = endMs - (TREND_DAYS - 1) * DAY_MS;
  const buckets = Array.from({ length: TREND_DAYS }, (_, i) => {
    const d = new Date(start + i * DAY_MS);
    return { day: d.toLocaleDateString(undefined, { month: "short", day: "numeric" }), count: 0 };
  });
  for (const ev of events) {
    const t = Date.parse(ev.occurred_at);
    if (Number.isNaN(t) || t < start - DAY_MS) continue;
    buckets[Math.min(TREND_DAYS - 1, Math.max(0, Math.floor((t - start) / DAY_MS)))].count += 1;
  }
  return buckets;
}

export default function ManagementPage() {
  const state = useFetch(fetchOverview);
  const loading = state.status === "loading";
  const data = state.status === "live" ? state.data : null;

  // Health is a secondary strip on its own fetch — a slow/failed cloud ping shows an
  // inline "unavailable" state instead of blanking the whole overview.
  const healthState = useFetch(getHealthDetailed);
  const health = healthState.status === "live" ? healthState.data : null;
  const healthLoading = healthState.status === "loading";
  const plantState = health?.overall ? label(health.overall) : healthState.status === "error" ? "Unavailable" : null;
  const plantTone = health?.overall === "healthy" ? "verified" : health?.overall === "degraded" ? "caution" : health?.overall === "down" ? "danger" : "info";

  const trendEndMs = useMemo(() => (data ? trendEnd(data.events) : null), [data]);
  const trend = useMemo(
    () => (data && trendEndMs !== null ? dailyCounts(data.events, trendEndMs) : null),
    [data, trendEndMs],
  );
  const trendSub =
    trendEndMs !== null && nowMs() - trendEndMs > DAY_MS
      ? `Daily volume, ${TREND_DAYS} days to ${new Date(trendEndMs).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}`
      : `Daily volume, last ${TREND_DAYS} days`;
  // All-zero series draws a misleading flat line — show nothing instead.
  const spark = useMemo(() => {
    const s = trend?.map((b) => b.count);
    return s?.some((v) => v > 0) ? s : undefined;
  }, [trend]);

  const overdueSla = data?.sla ? data.sla.overdue_conflicts_total + data.sla.overdue_quarantine_total : null;
  const criticalGaps = data?.compliance?.total_gaps.critical ?? null;

  const { ref: attentionRef, revealed: attentionRevealed } = useScrollReveal<HTMLDivElement>();
  const { ref: signalsRef, revealed: signalsRevealed } = useScrollReveal<HTMLDivElement>();
  const revealCls = (revealed: boolean) =>
    `min-w-0 transition-all duration-500 ${revealed ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"}`;

  return (
    <div data-testid="overview-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader
        eyebrow="Cross-functional"
        title="Plant overview"
        lede="Situational awareness across knowledge, conflicts, and compliance."
        actions={
          <>
            <Link
              href="/management/cross-site"
              className="inline-flex min-h-11 items-center rounded-lg border border-line px-3 text-caption font-semibold text-ink outline-offset-2 hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent"
            >
              Cross-site patterns
            </Link>
            <Link
              href="/management/plant-state"
              className="inline-flex min-h-11 items-center rounded-lg outline-offset-2 focus-visible:outline-2 focus-visible:outline-accent"
            >
              <StatusBadge tone={plantTone}>Plant state{plantState ? ` · ${plantState}` : ""}</StatusBadge>
            </Link>
          </>
        }
      />

      {state.status === "error" ? (
        <section data-testid="overview-error" className="mt-6 rounded-xl border border-line bg-surface p-8 text-center">
          <p className="text-body font-medium text-ink">Couldn&apos;t load the overview.</p>
          <p className="mt-1 text-caption text-muted">{state.error.message}</p>
          <button
            type="button"
            onClick={state.retry}
            className="mt-4 inline-flex min-h-11 items-center rounded-lg border border-line bg-surface-2 px-4 text-caption font-medium text-ink transition-colors hover:bg-canvas"
          >
            Retry
          </button>
        </section>
      ) : (
        <>
          {/* KPI strip — deep-linked tiles; numbers count up as live data lands */}
          <div data-testid="overview-kpis" className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <MetricCard label="Open conflicts" value={data?.conflictsTotal} sub="awaiting resolution" tone="caution" href="/governance/conflicts" loading={loading} />
            <MetricCard label="Quarantine backlog" value={data?.quarantineTotal} sub="items in review queue" tone="info" href="/governance/quarantine" loading={loading} />
            <MetricCard label="Overdue SLA items" value={overdueSla} sub="past deadline" tone="danger" href="/governance/sla" loading={loading} />
            <MetricCard label="Critical gaps" value={criticalGaps} sub="compliance findings" tone={criticalGaps === 0 ? "verified" : "danger"} href="/compliance" loading={loading} />
          </div>

          {/* Event volume trend — the page's live pulse (AC10 waived: chart stays) */}
          <div className="mt-4">
            <ChartCard
              title="Operational events"
              sub={trendSub}
              height={180}
              loading={trend === null}
              empty={trend !== null && trend.every((b) => b.count === 0) && "No events in this window."}
            >
              <AreaChart data={trend ?? []} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="event-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="day" {...AXIS} interval="preserveStartEnd" minTickGap={24} />
                <YAxis {...AXIS} allowDecimals={false} width={36} />
                <Tooltip {...TOOLTIP} />
                <Area type="monotone" dataKey="count" name="Events" stroke="var(--accent)" strokeWidth={2} fill="url(#event-fill)" dot={false} />
              </AreaChart>
            </ChartCard>
          </div>

          {/* Triage (wider) + signals feed — two independent column stacks so a
              short attention card never strands blank space beside the feed. */}
          <div data-testid="overview-priority-layout" className="mt-4 grid items-stretch gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <div ref={attentionRef} className={revealCls(attentionRevealed)}>
              <AttentionList sla={data?.sla ?? null} compliance={data?.compliance ?? null} loading={loading} />
              <HealthStrip health={health} loading={healthLoading} />
            </div>
            <div ref={signalsRef} className={`${revealCls(signalsRevealed)} h-full`} style={{ transitionDelay: "100ms" }}>
              <SignalsFeed events={data?.events ?? []} spark={spark} loading={loading} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
