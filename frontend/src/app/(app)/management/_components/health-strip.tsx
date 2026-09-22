import { Skeleton } from "@/components/skeleton";
import { StatusBadge } from "@/components/ui";
import type { HealthDetailed, ServiceHealth } from "@/lib/types";
import { capitalize } from "@/lib/utils";

const STATUS_RANK: Record<ServiceHealth["status"], number> = { down: 0, degraded: 1, healthy: 2 };
const OVERALL_TONE = { healthy: "verified", degraded: "caution", down: "danger" } as const;

/** Per-service health chips from GET /health/detailed — degraded/down first. */
export function HealthStrip({ health, loading = false }: { health: HealthDetailed | null; loading?: boolean }) {
  const services = [...(health?.services ?? [])].sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status]);
  return (
    <section data-testid="overview-health" className="mt-4 rounded-xl border border-line bg-surface p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">System health</h2>
        {health?.overall && (
          <StatusBadge tone={OVERALL_TONE[health.overall]}>
            {capitalize(health.overall)}
          </StatusBadge>
        )}
      </div>
      {loading ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9 w-32 rounded-md" />)}
        </div>
      ) : services.length === 0 ? (
        <p className="mt-3 text-caption text-muted">Live service status is unavailable.</p>
      ) : (
        // Cell mesh, as the landing lays out its system grid: one service per cell.
        <div className="mesh stagger mt-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
          {services.map((s) => (
            <div
              key={s.name}
              title={[s.details, s.latency_ms != null ? `${Math.round(s.latency_ms)} ms` : null].filter(Boolean).join(" · ") || undefined}
              className="flex min-w-0 items-center gap-2 bg-surface px-3 py-2.5 text-caption"
            >
              <span
                className={`size-1.5 shrink-0 ${s.status === "healthy" ? "bg-verified" : s.status === "degraded" ? "bg-caution" : "bg-danger"}`}
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1 truncate text-ink" title={s.name}>{s.name}</span>
              <span className={s.status === "healthy" ? "sr-only" : s.status === "degraded" ? "shrink-0 capitalize text-caution" : "shrink-0 capitalize text-danger"}>{s.status}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
