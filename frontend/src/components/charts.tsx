"use client";

// Recharts wrappers themed for the Paper palette. Import ONLY from page-level
// components that actually render a chart — recharts is heavy and Next
// code-splits it per route as long as ui.tsx never imports this file.
// Colors are passed as `var(--token)` strings: SVG presentation attributes
// resolve CSS custom properties live, so both palettes work with no JS resync.
import { Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import { useState } from "react";
import { ResponsiveContainer } from "recharts";

import { Icon } from "@/components/icon";
/** Shared axis defaults — recessive ticks, no axis/tick lines. Spread onto XAxis/YAxis. */
export const AXIS = {
  tick: { fontSize: 11, fill: "var(--muted)" },
  tickLine: false,
  axisLine: false,
} as const;

/** Shared grid defaults. Spread onto CartesianGrid. */
export const GRID = {
  strokeDasharray: "3 3",
  stroke: "var(--line)",
  vertical: false,
} as const;

/** Shared tooltip defaults. Spread onto Tooltip. */
export const TOOLTIP = {
  contentStyle: {
    background: "var(--surface)",
    border: "1px solid var(--line)",
    borderRadius: 0,
    fontSize: 12,
    color: "var(--ink)",
    // Strong enough to lift the tooltip off a dark canvas too, where a 0.08 wash is invisible.
    boxShadow: "0 8px 24px rgb(0 0 0 / 0.35)",
  },
  labelStyle: { color: "var(--muted)", fontWeight: 600 },
  cursor: { stroke: "var(--line)" },
} as const;

/** Series palette — identity colors for multi-series charts, in fixed assignment
 *  order (never cycled; >4 series folds into "Other"). Status tones (danger/
 *  caution/verified) stay reserved for status-encoded charts. */
export const SERIES = ["var(--accent)", "var(--info)", "var(--verified)", "var(--muted)"] as const;

/** Status/brand tone name → CSS token, for per-item chart coloring. */
export const TONE_VAR = {
  accent: "var(--accent)",
  danger: "var(--danger)",
  caution: "var(--caution)",
  verified: "var(--verified)",
  info: "var(--info)",
  neutral: "var(--muted)",
} as const;

export type ChartTone = keyof typeof TONE_VAR;

/** Cap chart data size — stride-sample, always keeping first and last points.
 *  ponytail: stride can miss narrow spikes; swap for LTTB if peaks start mattering. */
export function downsample<T>(data: T[], max = 500): T[] {
  if (data.length <= max) return data;
  const step = Math.ceil(data.length / max);
  const out = data.filter((_, i) => i % step === 0);
  if (out[out.length - 1] !== data[data.length - 1]) out.push(data[data.length - 1]);
  return out;
}

/** Card chrome for a chart: title row (+ optional right control), then the plot
 *  in a fixed-height ResponsiveContainer. State machine: loading → error →
 *  empty → ready; children mount ONLY when ready, so recharts runs its mount
 *  animation on real data (never a skeleton→data swap). Fixed body height =
 *  no layout shift between states. */
export function ChartCard({
  title,
  sub,
  control,
  height = 240,
  loading = false,
  empty,
  error,
  onRetry,
  collapsible = false,
  defaultOpen = true,
  className,
  children,
}: {
  title: string;
  sub?: string;
  /** Right-aligned header control (select, tabs…). */
  control?: React.ReactNode;
  height?: number;
  loading?: boolean;
  /** Message shown instead of the plot when the data is empty. */
  empty?: string | false;
  /** Error state — string is shown as the message; `true` uses a default. */
  error?: string | boolean;
  /** Renders a Retry button in the error state. */
  onRetry?: () => void;
  /** Chevron toggle collapsing the plot body. */
  collapsible?: boolean;
  defaultOpen?: boolean;
  className?: string;
  children: React.ReactElement;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const expanded = !collapsible || open;

  return (
    <section className={cn("rounded-xl border border-line bg-surface p-4", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-body font-semibold text-ink">{title}</h2>
          {sub && <p className="mt-0.5 text-caption text-muted">{sub}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {control}
          {collapsible && (
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              aria-label={open ? `Collapse ${title}` : `Expand ${title}`}
              className="grid size-7 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-ink"
            >
              <Icon name="caret-down" size={12} className={cn("transition-transform", !open && "-rotate-90")} />
            </button>
          )}
        </div>
      </div>
      {expanded && (
        <div className={cn("mt-3", collapsible && "animate-[page-in_200ms_ease-out]")} style={{ height }}>
          {loading ? (
            <Skeleton className="h-full w-full" />
          ) : error ? (
            <div className="flex h-full flex-col items-center justify-center gap-2">
              <p className="text-caption text-muted">{typeof error === "string" ? error : "Couldn't load this chart."}</p>
              {onRetry && (
                <Button variant="ghost" className="h-7 px-2.5 text-caption" onClick={onRetry}>
                  Retry
                </Button>
              )}
            </div>
          ) : empty ? (
            <p className="grid h-full place-items-center text-caption text-muted">{empty}</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              {children}
            </ResponsiveContainer>
          )}
        </div>
      )}
    </section>
  );
}

// Redesign-v2 spec name for the same component.
export { ChartCard as ChartContainer };
