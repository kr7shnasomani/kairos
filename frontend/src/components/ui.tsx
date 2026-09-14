"use client";

import Link from "next/link";
import type { AuthorityLevel, AuditLogEntry, BriefSource } from "@/lib/types";
import { getHealthDetailed } from "@/lib/api";
import { authorityLabel, cn } from "@/lib/utils";
import { fmtRelTime } from "@/lib/format";
import { useCountUp } from "@/lib/motion";
import { MetricCardSkeleton, TableSkeleton } from "@/components/skeleton";
import { useEffect, useId, useMemo, useRef, useState } from "react";

type Tone = "danger" | "caution" | "verified" | "info" | "validation" | "neutral";

/**
 * DESIGN.md §5.1 — exact value primary, relative time as the hint beneath.
 * Review item 28: "1d ago" is not enough for a compliance audit. Every
 * endpoint returns ISO-8601 with microsecond precision, so this is pure
 * formatting.
 */
export function Timestamp({
  value,
  relative = true,
  className,
}: {
  value: string | null | undefined;
  relative?: boolean;
  className?: string;
}) {
  if (!value) return <span className="text-muted">—</span>;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return <span className="text-muted">—</span>;

  const pad = (n: number) => String(n).padStart(2, "0");
  const exact =
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;

  return (
    <span title={value} className={cn("inline-flex flex-col leading-tight", className)}>
      <span className="tabular text-body text-ink">{exact}</span>
      {relative && <span className="text-caption text-muted">{fmtRelTime(value)}</span>}
    </span>
  );
}

/**
 * status string -> Tone. DESIGN.md 2.3, review items 13 and 26.
 *
 * Callers used to hand-pick a tone per call site, which is how `low` ended
 * up rendered in black — giving the least-severe level the most visual
 * weight. Severity now maps in one place.
 */
export function statusTone(status: string | null | undefined): Tone {
  if (!status) return "neutral";
  return STATUS_TONE[status.toLowerCase()] ?? "neutral";
}

const STATUS_TONE: Record<string, Tone> = {
  // fault / refusal / missed deadline
  open: "danger", overdue: "danger", critical: "danger", failed: "danger",
  disputed: "danger", rejected: "danger", safety_critical: "danger", refused: "danger",
  // awaiting action or review
  pending: "caution", pending_approval: "caution", pending_moc: "caution",
  quarantined: "caution", unverified: "caution", high: "caution", major: "caution",
  draft: "caution",
  // under monitoring / in flight
  monitor: "info", in_progress: "info", scheduled: "info", normal: "info",
  // under validation
  validation: "validation", under_review: "validation", questions_ready: "validation",
  // settled / healthy
  verified: "verified", approved: "verified", promoted: "verified",
  active: "verified", completed: "verified", resolved: "verified",
  // least weight — never danger
  low: "neutral", non_critical: "neutral", archived: "neutral",
  superseded: "neutral", cancelled: "neutral", decommissioned: "neutral",
};

/**
 * DESIGN.md 5.2 — truncate only when necessary, always expose the full value.
 * Review items 16, 18, 35, 37: truncation currently hides the one field that
 * identifies the record.
 */
export function Truncate({
  text,
  lines = 1,
  className,
}: {
  text: string | null | undefined;
  lines?: 1 | 2;
  className?: string;
}) {
  if (!text) return <span className="text-muted">—</span>;
  return (
    <span
      title={text}
      className={cn(lines === 2 ? "line-clamp-2" : "block truncate", "min-w-0", className)}
    >
      {text}
    </span>
  );
}

/**
 * A total and its own breakdown are distinct groups, not inline siblings.
 * Review item 9: /assets showed "Registered 4" beside the per-class counts
 * that sum to it, so the total read as just another class.
 */
export function KpiGroup({
  total,
  breakdown,
  breakdownLabel,
}: {
  total: { label: string; value: React.ReactNode };
  breakdown: { label: string; value: React.ReactNode }[];
  breakdownLabel?: string;
}) {
  return (
    <div className="flex flex-wrap items-stretch overflow-hidden rounded-lg border border-line bg-surface">
      <div data-testid="kpi-total" className="border-line px-5 py-4 sm:border-r">
        <div className="text-label uppercase tracking-wide text-muted">{total.label}</div>
        <div className="tabular text-display font-semibold leading-none text-ink">{total.value}</div>
      </div>
      <div data-testid="kpi-breakdown" className="flex min-w-0 flex-1 flex-col px-5 py-4">
        {breakdownLabel && (
          <div className="mb-2 text-label uppercase tracking-wide text-muted">{breakdownLabel}</div>
        )}
        <div className="flex flex-wrap gap-x-8 gap-y-3">
          {breakdown.map((b) => (
            <div key={b.label} className="min-w-0">
              <Truncate text={b.label} className="text-caption text-muted" />
              <div className="tabular text-subtitle font-semibold text-ink">{b.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const TONE_STYLE: Record<Tone, string> = {
  danger: "text-danger bg-[color-mix(in_srgb,var(--danger)_14%,transparent)]",
  caution: "text-caution bg-[color-mix(in_srgb,var(--caution)_16%,transparent)]",
  verified: "text-verified bg-[color-mix(in_srgb,var(--verified)_15%,transparent)]",
  info: "text-info bg-[color-mix(in_srgb,var(--info)_14%,transparent)]",
  validation: "text-validation bg-[color-mix(in_srgb,var(--validation)_14%,transparent)]",
  neutral: "text-muted bg-surface-2 border border-line",
};

/** Status pill — verification / severity. Dot encodes state in form, not just color. */
export function StatusBadge({
  tone,
  children,
  dot = true,
  pulse = false,
}: {
  tone: Tone;
  children: React.ReactNode;
  dot?: boolean;
  /** Subtle attention pulse on the dot — reserve for overdue/critical items. */
  pulse?: boolean;
}) {
  return (
    <span
      className={cn(
        // min-h (not fixed h) so a long label wraps *inside* the pill instead of
        // spilling out of it; single-line badges are unchanged at 22px.
        "inline-flex min-h-[22px] items-center gap-1.5 rounded-full px-2 py-0.5 text-label font-semibold leading-tight",
        TONE_STYLE[tone],
      )}
    >
      {dot && <span className={cn("size-1.5 shrink-0 rounded-full bg-current", pulse && "animate-pulse")} aria-hidden="true" />}
      {children}
    </span>
  );
}

/** Neutral mono chip carrying the authority level of a source. */
export function AuthorityBadge({ level }: { level: AuthorityLevel }) {
  return (
    <span className="tabular inline-flex h-[22px] items-center rounded-md border border-line bg-surface-2 px-2 text-label font-medium text-ink">
      {authorityLabel(level)}
    </span>
  );
}

/** Source reference chip — links to the vault document (accent-tinted). */
export function SourceChip({
  children,
  quarantine = false,
}: {
  children: React.ReactNode;
  quarantine?: boolean;
}) {
  return (
    <span
      className={cn(
        "tabular inline-flex h-[22px] items-center gap-1.5 rounded-md border px-2 text-label font-medium",
        quarantine
          ? "border-[color-mix(in_srgb,var(--caution)_35%,var(--line))] text-caution"
          : "border-[color-mix(in_srgb,var(--accent)_28%,var(--line))] text-accent",
      )}
    >
      {children}
    </span>
  );
}

/** Centered confirm dialog over a dimmed backdrop — refero: Medium/Clipchamp/Mercury confirms.
 *  Used for consequential writes (promote/dispute). Backdrop + Esc dismiss; focus trap; actions in children. */
export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    if (!panel) return;

    const focusables = () =>
      Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => !el.hasAttribute("disabled") && el.tabIndex !== -1);

    const first = focusables()[0];
    (first ?? panel).focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const list = focusables();
      if (list.length === 0) {
        e.preventDefault();
        return;
      }
      const firstEl = list[0];
      const lastEl = list[list.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    // No scroll lock. `overflow: hidden` on <html> takes the document out of the
    // scrollport, which kills `position: sticky` everywhere — measured live: the nav
    // rail jumped to railTop -900 the instant an overlay opened. Overlays are
    // position:fixed and their scroll panes use overscroll-contain, so the page
    // staying scrollable behind them is harmless; a broken rail is not.
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused.current?.focus?.();
    };
  }, []);

  // z-[200] tops every other overlay on purpose: action modals stack ON a slide-in panel
  // (quarantine ItemPanel is z-[100]), and underneath it the panel's scrim both dimmed the
  // modal and swallowed its clicks. A modal is the last thing opened, so it is always topmost.
  return (
    <div className="fixed inset-0 z-[200] grid place-items-center p-4" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <button type="button" className="absolute inset-0 animate-[overlay-in_150ms_ease-out] bg-[var(--scrim)]" aria-label="Close dialog" onClick={onClose} />
      <div
        ref={panelRef}
        tabIndex={-1}
        className="relative w-full max-w-md animate-[panel-in_150ms_ease-out] overflow-y-auto overscroll-contain rounded-xl border border-line bg-surface p-5 shadow-xl outline-none"
      >
        <div className="flex items-center justify-between gap-3">
          <h2 id={titleId} className="text-sm font-semibold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid size-7 place-items-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}

type ButtonVariant = "primary" | "ghost" | "danger";

export function Button({
  variant = "ghost",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      className={cn(
        "inline-flex h-9 items-center justify-center gap-2 rounded-lg px-3.5 text-body font-semibold transition duration-100 active:translate-y-px disabled:pointer-events-none disabled:opacity-50",
        variant === "primary"
          ? "bg-accent text-on-accent hover:brightness-105 active:brightness-95"
          : variant === "danger"
            ? "bg-danger text-white hover:brightness-105 active:brightness-95"
            : "border border-line text-ink hover:bg-surface-2 active:brightness-95",
        className,
      )}
      {...props}
    />
  );
}

// ─── Phase badge (Task 3) ────────────────────────────────────────────────────

const PHASE_LABELS: Record<string, string> = {
  "1": "Phase 1 · Retrieval",
  "2": "Phase 2 · Assisted",
  "3": "Phase 3 · Proactive",
};

/**
 * Deployment phase pill.
 *
 * Reads the phase the backend is **actually enforcing** (`GET /health/detailed`), not a frontend
 * build-time constant. It previously read `NEXT_PUBLIC_KAIROS_PHASE` with a default of "3", so a
 * deployment running in Phase 1 would still have claimed Phase 3 — and nothing consulted the
 * value on either side. Renders nothing until the live phase is known, so it can never assert a
 * phase it has not confirmed.
 */
export function PhaseBadge() {
  const [phase, setPhase] = useState<number | null>(null);
  useEffect(() => {
    let alive = true;
    getHealthDetailed()
      .then(({ data }) => { if (alive && typeof data?.phase === "number") setPhase(data.phase); })
      .catch(() => { /* health unreachable — say nothing rather than guess a phase */ });
    return () => { alive = false; };
  }, []);

  if (phase === null) return null;
  const label = PHASE_LABELS[String(phase)] ?? `Phase ${phase}`;
  return (
    <span className="inline-flex h-[20px] items-center rounded-full bg-[color-mix(in_srgb,var(--info)_14%,transparent)] px-2 text-micro font-semibold text-info">
      {label}
    </span>
  );
}

/** Honest data-source chip — shown when a page is rendering fixture/demo data. */
// ─── TrendDelta ──────────────────────────────────────────────────────────────

/** Signed percent-change chip. `invert` for metrics where up is bad (gaps, overdue). */
export function TrendDelta({ value, invert = false }: { value: number; invert?: boolean }) {
  if (value === 0) {
    return <span className="tabular text-label font-semibold text-muted">±0%</span>;
  }
  const up = value > 0;
  const good = invert ? !up : up;
  return (
    <span className={cn("tabular inline-flex items-center gap-0.5 text-label font-semibold", good ? "text-verified" : "text-danger")}>
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {up ? <path d="M6 15l6-6 6 6" /> : <path d="M6 9l6 6 6-6" />}
      </svg>
      {up ? "+" : ""}{value}%
    </span>
  );
}

// ─── Sparkline ───────────────────────────────────────────────────────────────

/** Inline trend line — pure SVG so ui.tsx stays free of the chart bundle.
 *  Colored via currentColor: wrap in a text-* tone class. */
export function Sparkline({
  data,
  width = 88,
  height = 26,
  className,
}: {
  data: number[];
  width?: number;
  height?: number;
  className?: string;
}) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const span = Math.max(...data) - min || 1;
  const points = data
    .map((v, i) => `${((i / (data.length - 1)) * (width - 2) + 1).toFixed(1)},${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={cn("shrink-0", className)} aria-hidden="true">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// ─── KpiCard (Task 4) ────────────────────────────────────────────────────────

/** Executive KPI tile — mono numeral, label, optional threshold colour,
 *  optional trend delta + sparkline. Numeric values count up on change. */
export function KpiCard({
  label,
  value,
  tone,
  sub,
  icon,
  onClick,
  href,
  loading = false,
  delta,
  invertDelta,
  spark,
}: {
  label: string;
  /** null/undefined renders an em dash — no metric ever shows "NaN"/"undefined". */
  value: string | number | null | undefined;
  tone?: "accent" | "danger" | "caution" | "verified" | "info" | "neutral";
  sub?: string;
  icon?: React.ReactNode;
  onClick?: () => void;
  /** Renders the tile as a Link with the interactive hover treatment. */
  href?: string;
  /** Renders MetricCardSkeleton with identical geometry (zero layout shift). */
  loading?: boolean;
  /** Percent change vs previous period — renders a TrendDelta chip. */
  delta?: number;
  /** Up is bad for this metric (open gaps, overdue items). */
  invertDelta?: boolean;
  /** Recent series for an inline sparkline. */
  spark?: number[];
}) {
  const valueColor =
    tone === "accent" ? "text-accent" :
    tone === "danger" ? "text-danger" :
    tone === "caution" ? "text-caution" :
    tone === "verified" ? "text-verified" :
    tone === "info" ? "text-info" :
    "text-ink";
  const markerStyle =
    tone === "accent" ? "bg-accent" :
    tone === "danger" ? "bg-danger" :
    tone === "caution" ? "bg-caution" :
    tone === "verified" ? "bg-verified" :
    tone === "info" ? "bg-info" :
    "bg-line";
  const surfaceStyle =
    tone === "accent" ? "bg-[color-mix(in_srgb,var(--accent)_5%,var(--surface))]" :
    tone === "danger" ? "bg-[color-mix(in_srgb,var(--danger)_5%,var(--surface))]" :
    tone === "caution" ? "bg-[color-mix(in_srgb,var(--caution)_5%,var(--surface))]" :
    tone === "verified" ? "bg-[color-mix(in_srgb,var(--verified)_4%,var(--surface))]" :
    tone === "info" ? "bg-[color-mix(in_srgb,var(--info)_4%,var(--surface))]" :
    "bg-surface";

  const numeric = typeof value === "number" ? value : null;
  const shown = useCountUp(numeric ?? 0);
  const display = numeric === null ? (value ?? "—") : Math.round(shown).toLocaleString();

  if (loading) return <MetricCardSkeleton />;

  const inner = (
    <>
      <span data-testid="kpi-accent" className={cn("absolute bottom-2 left-2 top-2 w-[3px] rounded-full", markerStyle)} aria-hidden="true" />
      <span className="flex items-start justify-between gap-3 pl-1">
        <span className="text-label font-medium uppercase tracking-[0.1em] text-muted">{label}</span>
        {icon && <span className={cn("shrink-0", valueColor)} aria-hidden="true">{icon}</span>}
      </span>
      <span className="flex items-end justify-between gap-2">
        <span className={cn("tabular pl-1 text-display font-semibold leading-none", valueColor)}>{display}</span>
        {spark && <Sparkline data={spark} className="text-accent opacity-70" />}
      </span>
      {(sub || delta !== undefined) && (
        <span className="flex items-center gap-2">
          {delta !== undefined && <TrendDelta value={delta} invert={invertDelta} />}
          {sub && <span className="text-label text-muted">{sub}</span>}
        </span>
      )}
    </>
  );
  const base = cn("group relative flex min-h-[104px] w-full flex-col gap-1 overflow-hidden rounded-xl border border-line px-5 py-4 text-left transition-colors", surfaceStyle);
  const interactive = "cursor-pointer transition-colors hover:border-accent/40 hover:bg-surface-2";

  if (href) {
    return (
      <Link href={href} className={cn(base, interactive)}>
        {inner}
      </Link>
    );
  }

  // Static stat tiles must not be announced as interactive controls.
  if (!onClick) return <div className={base}>{inner}</div>;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(base, interactive)}
    >
      {inner}
    </button>
  );
}

// Redesign-v2 spec name for the same tile.
export { KpiCard as MetricCard };

// ─── DataTable (Task 4) ──────────────────────────────────────────────────────

export interface TableColumn<T> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
  className?: string;
  /** Enables the sort toggle; sorts on this value (defaults to row[key]). */
  sortValue?: (row: T) => string | number;
  sortable?: boolean;
  /** Numeric columns right-align in BOTH header and cell (review item 10). */
  align?: "left" | "right";
  /**
   * TRAP: the table is `table-fixed`, where `max-width` on a cell is IGNORED and
   * only `width` counts. A `w-full` here means width:100%, so that column claims
   * the whole table and every sibling collapses to 0px -- the DOM still reports
   * five headers while the user sees one. This silently hid columns on six
   * tables (review items 8, 14, 32). Use an explicit percentage (`w-[38%]`).
   */
}

/** Dense data table — optional tri-state column sort, client pagination
 *  (sticky header, "Showing X–Y of N"), optional empty state and row click. */
export function DataTable<T extends Record<string, unknown>>({
  columns,
  rows,
  keyFn,
  emptyState,
  pageSize,
  onRowClick,
  loading = false,
  toolbar,
}: {
  columns: TableColumn<T>[];
  rows: T[];
  keyFn: (row: T) => string;
  emptyState?: React.ReactNode;
  /** Paginate past this many rows. Omit for a short, known-small list. */
  pageSize?: number;
  onRowClick?: (row: T) => void;
  /** Renders TableSkeleton sized to the real column count. */
  loading?: boolean;
  /** Filter/search row rendered above the header inside the table chrome. */
  toolbar?: React.ReactNode;
}) {
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(null);
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    const val = col?.sortValue ?? ((row: T) => row[sort.key] as string | number);
    return [...rows].sort((a, b) => {
      const av = val(a) ?? "";
      const bv = val(b) ?? "";
      const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }, [rows, sort, columns]);

  if (loading) {
    return <TableSkeleton rows={pageSize ? Math.min(pageSize, 10) : 8} cols={columns.length} />;
  }

  if (rows.length === 0 && emptyState) {
    return <>{emptyState}</>;
  }

  const pages = pageSize ? Math.ceil(sorted.length / pageSize) : 1;
  const safePage = Math.min(page, pages - 1);
  const visible = pageSize ? sorted.slice(safePage * pageSize, (safePage + 1) * pageSize) : sorted;

  function toggleSort(key: string) {
    setPage(0);
    setSort((s) =>
      s?.key !== key ? { key, dir: "asc" } :
      s.dir === "asc" ? { key, dir: "desc" } :
      null,
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      {toolbar && <div className="flex items-center gap-2 border-b border-line bg-surface px-3 py-2">{toolbar}</div>}
      <table className="w-full table-fixed text-body">
        <thead>
          <tr className="border-b border-line bg-surface-2">
            {columns.map((col) => (
              <th
                key={col.key}
                aria-sort={sort?.key === col.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}
                className={cn(
                  "sticky top-0 bg-surface-2 px-3 py-2.5 text-caption font-semibold text-muted overflow-hidden",
                  col.align === "right" ? "text-right" : "text-left",
                  col.className,
                )}
              >
                {col.sortable || col.sortValue ? (
                  <button
                    type="button"
                    onClick={() => toggleSort(col.key)}
                    className={cn("inline-flex items-center gap-1 hover:text-ink", col.align === "right" && "flex-row-reverse")}
                  >
                    {col.label}
                    {/* Review item 7: an up-caret on an unsorted column reads as
                        "sorted ascending". Inactive columns get a neutral
                        two-way glyph; only the sorted one claims a direction. */}
                    {sort?.key === col.key ? (
                      <svg data-sort-dir={sort.dir} width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        {sort.dir === "desc" ? <path d="M6 9l6 6 6-6" /> : <path d="M6 15l6-6 6 6" />}
                      </svg>
                    ) : (
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="opacity-25">
                        <path d="M8 9l4-4 4 4" /><path d="M8 15l4 4 4-4" />
                      </svg>
                    )}
                  </button>
                ) : (
                  col.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visible.map((row) => (
            <tr
              key={keyFn(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cn(
                "border-b border-line/60 bg-surface last:border-0",
                onRowClick && "cursor-pointer transition-colors hover:bg-surface-2",
              )}
            >
              {columns.map((col) => (
                <td key={col.key} className={cn("px-3 py-2 align-top overflow-hidden", col.align === "right" && "text-right", col.className)}>
                  {col.render ? col.render(row) : String(row[col.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {pageSize && sorted.length > pageSize && (
        <div className="flex items-center justify-between border-t border-line bg-surface-2 px-3 py-2">
          <span className="tabular text-label text-muted">
            Showing {safePage * pageSize + 1}–{Math.min((safePage + 1) * pageSize, sorted.length)} of {sorted.length}
          </span>
          <span className="flex gap-1">
            <Button className="h-7 px-2.5 text-caption" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>
              Prev
            </Button>
            <Button className="h-7 px-2.5 text-caption" disabled={safePage >= pages - 1} onClick={() => setPage(safePage + 1)}>
              Next
            </Button>
          </span>
        </div>
      )}
    </div>
  );
}

// ─── FilterTabs (Task 4) ─────────────────────────────────────────────────────

/** Segmented control for list filtering. */
export function FilterTabs({
  tabs,
  active,
  onChange,
}: {
  tabs: Array<{ key: string; label: string; count?: number }>;
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    // Mobile: single-row horizontal scroll (wrapping breaks the segmented look);
    // sm+: wrap as before.
    <div role="group" aria-label="Filters" className="flex gap-1 overflow-x-auto rounded-lg border border-line bg-surface-2 p-1 sm:flex-wrap">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          aria-pressed={active === tab.key}
          onClick={() => onChange(tab.key)}
          className={cn(
            "flex h-7 shrink-0 items-center gap-1.5 rounded-md px-3 text-caption font-semibold transition-colors",
            active === tab.key
              ? "bg-surface text-ink shadow-sm"
              : "text-muted hover:text-ink",
          )}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className="tabular rounded-full bg-surface-2 px-1.5 text-label text-muted">
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

// ─── Timeline (Task 4) ───────────────────────────────────────────────────────

export interface TimelineEvent {
  id: string;
  timestamp: string;
  label: string;
  description?: string;
  tone?: "danger" | "caution" | "verified" | "info" | "neutral";
  meta?: string;
}

/** Vertical event spine with a time gutter. Pure CSS, no library. */
export function Timeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) return <EmptyState message="No events to show." />;
  return (
    <ol className="relative space-y-4 pl-6">
      {/* spine — centered on the dots (both at x=8px) */}
      <div className="absolute inset-y-0 left-[7px] w-0.5 bg-line" aria-hidden="true" />
      {events.map((ev) => {
        const dotColor =
          ev.tone === "danger" ? "bg-danger" :
          ev.tone === "caution" ? "bg-caution" :
          ev.tone === "verified" ? "bg-verified" :
          ev.tone === "info" ? "bg-info" :
          "bg-muted";
        return (
          <li key={ev.id} className="relative">
            <span
              className={cn("absolute -left-[20px] top-[5px] size-2 rounded-full ring-2 ring-surface", dotColor)}
              aria-hidden="true"
            />
            <div>
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="text-body font-semibold text-ink">{ev.label}</span>
                <time className="tabular text-label text-muted">{ev.timestamp}</time>
                {ev.meta && (
                  <span className="text-label text-muted">{ev.meta}</span>
                )}
              </div>
              {ev.description && (
                <p className="mt-0.5 text-caption leading-snug text-muted">{ev.description}</p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// ─── EvidenceLineage (Task 4) ────────────────────────────────────────────────

/** Collapsible source + audit trail — shown under every AI answer and brief. */
export function EvidenceLineage({
  sources,
  auditEntries,
}: {
  sources?: BriefSource[];
  auditEntries?: AuditLogEntry[];
}) {
  const [open, setOpen] = useState(false);
  const total = (sources?.length ?? 0) + (auditEntries?.length ?? 0);
  if (total === 0) return null;

  return (
    <div className="rounded-lg border border-line bg-surface-2 text-caption">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-3 py-2 font-semibold text-muted hover:text-ink"
      >
        <span>Evidence lineage · {total} item{total !== 1 ? "s" : ""}</span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={cn("transition-transform", open && "rotate-180")}
          aria-hidden="true"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-line px-3 py-3 space-y-3">
          {sources && sources.length > 0 && (
            <div>
              <p className="mb-1.5 text-label font-bold uppercase tracking-[0.1em] text-muted">Sources</p>
              <ul className="space-y-2">
                {sources.map((s, i) => (
                  <li key={`${s.document_id}-${i}`} className="flex flex-wrap items-center gap-1.5">
                    <SourceChip quarantine={s.is_quarantine}>{s.title || s.document_id}</SourceChip>
                    <AuthorityBadge level={s.authority_level} />
                    {s.is_quarantine && (
                      <StatusBadge tone="caution" dot={false}>Unverified</StatusBadge>
                    )}
                    {s.vault_url && (
                      <a
                        href={s.vault_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-label text-accent underline hover:no-underline"
                      >
                        Vault ↗
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {auditEntries && auditEntries.length > 0 && (
            <div>
              <p className="mb-1.5 text-label font-bold uppercase tracking-[0.1em] text-muted">Audit Trail</p>
              <ul className="space-y-1">
                {auditEntries.map((e) => (
                  <li key={e.log_id} className="flex flex-wrap gap-2 text-label text-muted">
                    <time className="tabular shrink-0">{new Date(e.timestamp).toLocaleString()}</time>
                    <span className="font-medium text-ink">{e.action}</span>
                    <span>by {e.performed_by}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── ConfidenceMeter (Task 4) ────────────────────────────────────────────────

/** 0–1 confidence bar with verified / caution / danger banding. */
/** `value: null` means the model reported no confidence — NOT that confidence is zero.
 *  Coercing the two together is how a perfectly good answer ended up wearing a "0%" badge:
 *  ~23% of successful syntheses return no parseable CONFIDENCE marker. A meter cannot express
 *  "unknown", so this renders a plain unmeasured state instead of a bar at 0. */
export function ConfidenceMeter({ value }: { value: number | null }) {
  if (value == null) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-label font-semibold text-muted">Confidence not reported</span>
        <span className="text-label text-muted">— judge this answer on its sources</span>
      </div>
    );
  }
  const pct = Math.min(100, Math.max(0, Math.round(value * 100)));
  const tone =
    value >= 0.85 ? "bg-verified" :
    value >= 0.7 ? "bg-caution" :
    "bg-danger";
  const label =
    value >= 0.85 ? "verified" :
    value >= 0.7 ? "caution" :
    "danger";

  return (
    <div className="flex items-center gap-2">
      <div
        className="relative h-1.5 flex-1 rounded-full bg-surface-2"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Confidence ${pct}%`}
      >
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${pct}%` }} />
      </div>
      <span className="tabular text-label font-semibold text-muted">{pct}%</span>
      <StatusBadge tone={label} dot={false}>{label}</StatusBadge>
    </div>
  );
}

// ─── RefusalCard (Task 4) ────────────────────────────────────────────────────

/** Safety-critical explicit refusal — never a hedged answer. */
export function RefusalCard({
  reason,
  sources,
  escalateTo,
}: {
  reason?: string;
  sources?: BriefSource[];
  escalateTo?: string;
}) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-danger/30 bg-[color-mix(in_srgb,var(--danger)_8%,transparent)] p-4 space-y-3"
    >
      <div className="flex items-start gap-2.5">
        <svg
          className="mt-0.5 size-4 shrink-0 text-danger"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <div>
          <p className="text-body font-semibold text-danger">Safety-critical query — sources returned directly</p>
          {reason && <p className="mt-0.5 text-caption text-muted">{reason}</p>}
        </div>
      </div>

      {sources && sources.length > 0 && (
        <div>
          <p className="mb-1.5 text-label font-bold uppercase tracking-[0.1em] text-muted">Relevant sources</p>
          <ul className="space-y-1.5">
            {sources.map((s, i) => (
              <li key={`${s.document_id}-${i}`} className="flex flex-wrap items-center gap-1.5">
                <SourceChip quarantine={s.is_quarantine}>{s.title || s.document_id}</SourceChip>
                <AuthorityBadge level={s.authority_level} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {escalateTo && (
        <p className="text-caption text-muted">
          Escalate to: <span className="font-semibold text-ink">{escalateTo}</span>
        </p>
      )}
    </div>
  );
}

// ─── EmptyState (Task 4) ─────────────────────────────────────────────────────

/** Icon + message + optional CTA for empty list / no results states. */
/** Standard page header — eyebrow · title · lede · right-aligned actions.
 *  One h1 voice across the app: display (28px) for workspaces, title (20px)
 *  via `compact` for detail views. Use this instead of hand-rolled headers
 *  so typography can't drift page-to-page. */
export function PageHeader({
  eyebrow,
  title,
  lede,
  actions,
  compact,
  className,
}: {
  eyebrow?: string;
  title: React.ReactNode;
  lede?: React.ReactNode;
  actions?: React.ReactNode;
  compact?: boolean;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        {eyebrow && <p className="text-label font-bold uppercase tracking-[0.1em] text-accent">{eyebrow}</p>}
        <h1 className={cn("mt-1 font-semibold leading-tight text-balance", compact ? "text-title" : "text-display")}>
          {title}
        </h1>
        {lede && <p className="mt-1.5 max-w-prose text-body text-muted text-pretty">{lede}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function EmptyState({
  message,
  action,
}: {
  message: string;
  // href renders a Link (works in server components); onClick renders a button
  action?: { label: string; onClick: () => void } | { label: string; href: string };
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-line py-12 text-center">
      <svg
        className="size-8 text-muted/40"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="10" />
        <path d="M12 8v4M12 16h.01" />
      </svg>
      <p className="text-body text-muted">{message}</p>
      {action && ("href" in action ? (
        <Link
          href={action.href}
          className="inline-flex h-8 items-center rounded-lg border border-line bg-surface px-3 text-caption font-medium text-ink transition-colors hover:border-[color-mix(in_srgb,var(--accent)_40%,var(--line))] hover:bg-surface-2"
        >
          {action.label}
        </Link>
      ) : (
        <Button variant="ghost" onClick={action.onClick}>
          {action.label}
        </Button>
      ))}
    </div>
  );
}
