"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getConflicts, getQuarantine } from "@/lib/api";
import { KpiCard, PageHeader, StatusBadge, statusTone } from "@/components/ui";

type SurfaceKey = "conflicts" | "quarantine" | "moc" | "sla" | "timestamp-drift" | "push-volume-gate" | "circuit-breaker" | "model-gate";

const SURFACES: Array<{ key: SurfaceKey; href: string; group: string; title: string; desc: string }> = [
  {
    key: "conflicts",
    href: "/governance/conflicts",
    group: "Adjudication",
    title: "Conflicts",
    desc: "Resolve administrative contradictions or route engineering-track decisions through Management of Change.",
  },
  {
    key: "quarantine",
    href: "/governance/quarantine",
    group: "Adjudication",
    title: "Quarantine",
    desc: "Review unverified field inputs before they can enter the canonical knowledge graph.",
  },
  {
    key: "moc",
    href: "/governance/moc",
    group: "Adjudication",
    title: "Management of Change",
    desc: "Review engineering-track changes, blast radius, and the human sign-off that closes old facts.",
  },
  {
    key: "sla",
    href: "/governance/sla",
    group: "Oversight",
    title: "SLA report",
    desc: "Track overdue governance decisions, countdowns, and escalation state across active queues.",
  },
  {
    key: "timestamp-drift",
    href: "/governance/timestamp-drift",
    group: "Oversight",
    title: "Timestamp drift",
    desc: "Check clock disagreement between source systems that recorded the same physical event.",
  },
  {
    key: "push-volume-gate",
    href: "/governance/push-volume-gate",
    group: "Oversight",
    title: "Push-volume gate",
    desc: "Confirm briefs per operator stay within the EEMUA 191 hourly ceiling before proactive mode is the default.",
  },
  {
    key: "circuit-breaker",
    href: "/governance/circuit-breaker",
    group: "Safeguards",
    title: "Circuit Breaker",
    desc: "Inspect anomaly gates that halt ingestion until an administrator reviews the affected asset class.",
  },
  {
    key: "model-gate",
    href: "/governance/model-gate",
    group: "Safeguards",
    title: "Model Gate",
    desc: "Review validation precision and recall before a model is allowed to move into production.",
  },
];

interface Overview {
  openConflicts: number;
  engineeringConflicts: number;
  pendingMoc: number;
  pendingQuarantine: number;
  overdue: number;
}

export default function GovernancePage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    Promise.all([getConflicts(), getQuarantine()]).then(([conflicts, quarantine]) => {
      if (!alive) return;
      // Live-only is enforced in the fetchers now — they throw instead of returning a
      // fixture, so a failure lands in .catch() and the counts stay blank with a retry.
      setFailed(false);
      const openConflicts = conflicts.data.items.filter((item) => item.status !== "resolved");
      const pendingQuarantine = quarantine.data.items.filter((item) => item.review_status === "pending");
      setOverview({
        openConflicts: openConflicts.length,
        engineeringConflicts: openConflicts.filter((item) => item.track === "engineering").length,
        pendingMoc: openConflicts.filter((item) => item.status === "pending_moc").length,
        // Use the query total, not items.length — the fetch is capped at limit=50,
        // so a 59-item pending queue would otherwise under-report as 50.
        pendingQuarantine: quarantine.data.total ?? pendingQuarantine.length,
        overdue: openConflicts.filter((item) => item.is_overdue).length + pendingQuarantine.filter((item) => item.is_overdue).length,
      });
    }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [reload]);

  // First load = no data yet and no error → show skeletons, not em-dashes.
  const loading = overview === null && !failed;
  const value = (key: keyof Overview) => overview?.[key] ?? "—";
  // Review item 26: the tone comes from statusTone() so this page cannot drift from
  // the app-wide STATUS_TONE map. A zero count stays neutral on purpose — nothing
  // pending is not a state worth colouring.
  const statusFor = (key: SurfaceKey): { label: string; tone: ReturnType<typeof statusTone> } => {
    if (loading) return { label: "···", tone: "neutral" };
    if (key === "conflicts") return { label: `${value("openConflicts")} open`, tone: overview?.openConflicts ? statusTone("open") : "neutral" };
    if (key === "quarantine") return { label: `${value("pendingQuarantine")} pending`, tone: overview?.pendingQuarantine ? statusTone("pending") : "neutral" };
    if (key === "moc") return { label: `${value("pendingMoc")} pending`, tone: overview?.pendingMoc ? statusTone("pending") : "neutral" };
    if (key === "sla") return { label: `${value("overdue")} overdue`, tone: overview?.overdue ? statusTone("overdue") : "neutral" };
    if (key === "timestamp-drift" || key === "push-volume-gate") return { label: "Report", tone: statusTone("monitor") };
    return key === "circuit-breaker"
      ? { label: "Monitor", tone: statusTone("monitor") }
      : { label: "Validation", tone: statusTone("validation") };
  };
  const ctaFor = (key: SurfaceKey, status: ReturnType<typeof statusFor>) => {
    if (key === "conflicts") return `Review ${status.label} conflicts`;
    if (key === "quarantine") return `Review ${status.label} inputs`;
    if (key === "moc") return `Review ${status.label} changes`;
    if (key === "sla") return `Inspect ${status.label} decisions`;
    if (key === "timestamp-drift") return "Inspect clock drift";
    if (key === "push-volume-gate") return "Check push volume";
    return key === "circuit-breaker" ? "Inspect anomaly gates" : "Review model validation";
  };

  return (
    <div data-testid="governance-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader
        eyebrow="Layer 7 · Dual-track governance"
        title="Governance"
        lede="Where contradictions surface, unverified inputs are gated, and human authority decides what becomes canonical truth."
      />

      <div className="mt-3 flex flex-wrap items-center gap-3 text-caption text-muted">
        <span>Adjudication · oversight · safeguards</span>
        {failed && (
          <button type="button" onClick={() => setReload((r) => r + 1)} className="font-medium text-accent hover:underline">
            Live counts unavailable — retry
          </button>
        )}
      </div>

      <div data-testid="governance-summary" className="mt-6 rounded-xl border border-line bg-surface p-3 shadow-sm">
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <KpiCard label="Open conflicts" value={value("openConflicts")} sub="Awaiting decision" tone={overview?.openConflicts ? "danger" : "neutral"} loading={loading} />
          <KpiCard label="Engineering track" value={value("engineeringConflicts")} sub="Human sign-off" tone={overview?.engineeringConflicts ? "caution" : "neutral"} loading={loading} />
          <KpiCard label="Pending quarantine" value={value("pendingQuarantine")} sub="Unverified inputs" tone={overview?.pendingQuarantine ? "caution" : "neutral"} loading={loading} />
          <KpiCard label="Overdue" value={value("overdue")} sub="Across active queues" tone={overview?.overdue ? "danger" : "neutral"} loading={loading} />
        </div>
      </div>

      <div className="mt-6 flex items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Governance controls</h2>
          <p className="text-caption text-muted">Open a queue to review evidence, make a decision, or inspect a safeguard.</p>
        </div>
        <span className="tabular shrink-0 text-caption text-muted">{SURFACES.length} controls</span>
      </div>

      <div data-testid="governance-surfaces" className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {SURFACES.map((surface) => {
          const status = statusFor(surface.key);
          const cta = ctaFor(surface.key, status);
          return (
            <Link
              key={surface.key}
              href={surface.href}
              data-testid={`governance-surface-${surface.key}`}
              className="group flex min-h-44 flex-col rounded-xl border border-line bg-surface p-5 shadow-sm transition duration-150 hover:-translate-y-0.5 hover:border-[color-mix(in_srgb,var(--accent)_35%,var(--line))] hover:shadow-md"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-label font-semibold uppercase tracking-[0.1em] text-muted">{surface.group}</span>
                <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
              </div>
              <h3 className="mt-4 text-subtitle font-semibold text-ink">{surface.title}</h3>
              <p className="mt-1.5 text-body leading-relaxed text-muted">{surface.desc}</p>
              <span className="mt-auto pt-4 text-caption font-semibold text-accent">{cta} <span className="inline-block transition-transform group-hover:translate-x-0.5">→</span></span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
