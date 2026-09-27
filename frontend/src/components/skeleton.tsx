import { cn } from "@/lib/utils";

/** Low-fatigue loading placeholder. Pulse on the surface-2 tone (both themes). */
export function Skeleton({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={cn("animate-pulse rounded-md bg-surface-2", className)} style={style} aria-hidden="true" />;
}

/** Matches MetricCard geometry exactly (min-h, padding, bars) — zero layout
 *  shift when the real value replaces it. */
export function MetricCardSkeleton() {
  return (
    <div className="flex min-h-[96px] w-full flex-col gap-2 border border-line bg-surface px-5 py-4" aria-hidden="true">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-2 h-10 w-20" />
    </div>
  );
}

/** Fixed-height plot placeholder — pair with ChartCard's body height. */
export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return <Skeleton className="w-full" style={{ height }} />;
}

/** Table placeholder: header bar + row bars, sized to the real column count. */
export function TableSkeleton({ rows = 8, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line" aria-hidden="true">
      <div className="flex gap-3 border-b border-line bg-surface-2 px-3 py-2.5">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3 border-b border-line/60 bg-surface px-3 py-3 last:border-0">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-3.5 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Stacked card rows for list pages. */
export function ListSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-16 w-full rounded-xl" />
      ))}
    </div>
  );
}

/** Detail-page placeholder: title block + meta row + two content panels. */
export function DetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-3 h-8 w-64" />
      <div className="mt-3 flex gap-2">
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-5 w-24" />
      </div>
      <Skeleton className="mt-6 h-40 w-full rounded-xl" />
      <Skeleton className="mt-4 h-64 w-full rounded-xl" />
    </div>
  );
}

/** Page-level skeleton matching the standard content container (header + list rows). */
export function PageSkeleton() {
  return (
    <div className="mx-auto max-w-3xl" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-3 h-8 w-56" />
      <Skeleton className="mt-3 h-4 w-full max-w-md" />
      <div className="mt-6 space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full rounded-xl" />
        ))}
      </div>
    </div>
  );
}
