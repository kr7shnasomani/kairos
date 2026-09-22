// Lists offboarding programmes — structured knowledge-transfer sessions for departing experts.
import Link from "next/link";
import { getOffboardingList } from "@/lib/api";
import { PageHeader, StatusBadge } from "@/components/ui";
import { label, plural } from "@/lib/labels";

function progressBar(done: number, total: number) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="mt-4">
      <div className="mb-1.5 flex items-center justify-between gap-3 text-label text-muted">
        <span className="tabular">{done} of {total} {total === 1 ? "session" : "sessions"}</span>
        <span className="tabular font-semibold text-ink">{pct}%</span>
      </div>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
        <div
          className="h-full bg-accent transition-[width] duration-300 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// This page is a server component, so it cannot CALL statusTone() — that lives in
// the "use client" ui.tsx, and a client function can only be rendered as a
// component or passed as a prop, never invoked from the server. StatusBadge is a
// component and crosses the boundary fine; the tone mapping is local instead.
// Live data is `scheduled` for all 17 programmes; the rest mirror ui.tsx's
// STATUS_TONE so the two never disagree if the backend widens the domain.
type BadgeTone = "info" | "verified" | "caution" | "danger" | "neutral";
const PROGRAMME_TONE: Record<string, BadgeTone> = {
  scheduled: "info",
  in_progress: "info",
  completed: "verified",
  cancelled: "neutral",
  overdue: "danger",
};
function programmeTone(status: string | null | undefined): BadgeTone {
  if (!status) return "neutral";
  return PROGRAMME_TONE[status.toLowerCase()] ?? "neutral";
}

function programmeIdentifier({ personnel_email, personnel_id }: { personnel_email?: string | null; personnel_id?: string | null }) {
  return personnel_email?.trim() || personnel_id?.trim() || "No identifier available";
}

function retirementTiming(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;

  const today = new Date();
  const todayUtc = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  const days = Math.round((date.getTime() - todayUtc) / 86_400_000);
  return {
    absolute: date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }),
    relative: days < 0 ? `Retired ${plural(Math.abs(days), "day")} ago` : days === 0 ? "Retires today" : `Retires in ${plural(days, "day")}`,
    urgent: days >= 0 && days <= 30,
  };
}

function RetirementDate({ value }: { value: string | null | undefined }) {
  const timing = retirementTiming(value);
  if (!timing) return <p className="mt-0.5 text-label text-muted">Retirement date unavailable</p>;
  return (
    <div className="mt-0.5 flex flex-wrap gap-x-2 text-label">
      <time dateTime={value ?? undefined} title={value ?? undefined} className="text-muted">Retires {timing.absolute}</time>
      <span className={timing.urgent ? "text-caution" : "text-muted"}>{timing.relative}</span>
    </div>
  );
}

export default async function OffboardingPage() {
  const { data: programmes } = await getOffboardingList();
  const totalSessions = programmes.reduce((sum, programme) => sum + programme.total_sessions, 0);
  const completedSessions = programmes.reduce((sum, programme) => sum + (programme.sessions_completed ?? 0), 0);
  const completedProgrammes = programmes.filter((programme) => programme.total_sessions > 0 && (programme.sessions_completed ?? 0) === programme.total_sessions).length;
  const activeProgrammes = programmes.length - completedProgrammes;

  return (
    <div data-testid="offboarding-workspace" className="mx-auto max-w-[1400px]">
      <PageHeader
        eyebrow="Knowledge transfer"
        title="Expert handovers"
        lede="Structured knowledge transfer for departing experts: graph-derived sessions targeting top failure modes by equipment family."
      />

      <div data-testid="offboarding-summary" className="mt-6 grid overflow-hidden rounded-xl border border-line bg-surface shadow-sm sm:grid-cols-2 lg:grid-cols-[minmax(0,1.25fr)_repeat(3,minmax(130px,0.55fr))]">
        <div className="relative bg-[linear-gradient(120deg,color-mix(in_srgb,var(--info)_7%,var(--surface)),var(--surface))] px-5 py-5 sm:col-span-2 lg:col-span-1">
          <span aria-hidden="true" className="absolute bottom-3 left-2 top-3 w-[3px] bg-info" />
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-label font-semibold uppercase tracking-[0.1em] text-muted">Handover coverage</p>
          </div>
          <p className="tabular mt-1 text-title font-semibold text-ink">{activeProgrammes} active programmes</p>
          <p className="mt-1 text-label text-muted">Knowledge capture ahead of retirement</p>
        </div>
        <SummaryMetric value={completedProgrammes} label="complete" className="sm:border-r lg:border-l" />
        <SummaryMetric value={totalSessions} label="total sessions" />
        <div className="border-t border-line px-5 py-4 sm:col-span-2 lg:col-span-1 lg:border-l lg:border-t-0">
          <p className="tabular text-title font-semibold text-ink">{completedSessions} of {totalSessions} sessions</p>
          <p className="mt-1 text-label font-medium uppercase tracking-[0.08em] text-muted">captured</p>
        </div>
      </div>

      {programmes.length === 0 ? (
        <div className="mt-10 rounded-xl border border-line bg-surface px-6 py-12 text-center">
          <p className="text-sm font-semibold">No active programmes</p>
          <p className="mt-1 text-body text-muted">
            Programmes are created when a departing expert is registered with a retirement date.
          </p>
        </div>
      ) : (
        <div data-testid="offboarding-programmes" className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {programmes.map((p) => {
            const done = p.sessions_completed ?? 0;
            const total = p.total_sessions;
            const identifier = programmeIdentifier(p);
            return (
              <Link
                key={p.id}
                data-testid={`offboarding-programme-${p.id}`}
                href={`/offboarding/${p.id}`}
                className="lp-card group flex min-w-0 flex-col border border-line bg-surface p-5"
              >
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-body font-semibold text-link" title={identifier}>{identifier}</p>
                    <RetirementDate value={p.retirement_date} />
                  </div>
                  <StatusBadge tone={programmeTone(p.status)}>{label(p.status)}</StatusBadge>
                </div>
                {progressBar(done, total)}
                <span className="mt-4 text-caption font-semibold text-accent group-hover:underline">Open handover ›</span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SummaryMetric({ value, label, className = "" }: { value: number; label: string; className?: string }) {
  return (
    <div className={`border-t border-line px-5 py-4 lg:border-t-0 ${className}`}>
      <p className="tabular text-title font-semibold text-ink">{value}</p>
      <p className="mt-1 text-label font-medium uppercase tracking-[0.08em] text-muted">{label}</p>
    </div>
  );
}
