"use client";

import Link from "next/link";
import { StatusBadge, type TableColumn } from "@/components/ui";
import type { QuarantineItem, QuarantineStatus } from "@/lib/types";
import { relativeTime, slaCountdown, triggerLabel } from "@/lib/utils";

/** QuarantineItem re-mapped so it satisfies DataTable's Record constraint
 *  (interfaces have no implicit index signature; this Pick-mapped alias does). */
export type QuarantineRow = Pick<QuarantineItem, keyof QuarantineItem>;

const STATUS_META: Record<QuarantineStatus, { tone: "caution" | "verified" | "danger" | "neutral"; label: string }> = {
  pending: { tone: "caution", label: "Pending" },
  promoted: { tone: "verified", label: "Promoted" },
  disputed: { tone: "danger", label: "Disputed" },
  archived: { tone: "neutral", label: "Archived" },
};

export function SlaChip({ item, nowMs }: { item: QuarantineRow; nowMs: number }) {
  if (!item.sla_due_at || item.review_status !== "pending") return <span className="text-muted">—</span>;
  if (item.is_overdue) return <span className="tabular text-label font-semibold text-danger">SLA overdue</span>;
  const { label, tone } = slaCountdown(item.sla_due_at, nowMs);
  return <span className={`tabular text-label font-semibold ${tone}`}>{label}</span>;
}

export function formatContent(raw: string): string {
  if (!raw) return "—";
  try {
    if (raw.startsWith("{") || raw.startsWith("[")) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
         if (parsed[0].answer) return parsed[0].answer;
         if (parsed[0].question_index !== undefined) return `Q${parsed[0].question_index}: ${parsed[0].answer || ""}`;
      }
      if (parsed.answer) return parsed.answer;
      if (parsed.quarantine_id) return `Quarantine ID: ${parsed.quarantine_id}`;
      // fallback
      return JSON.stringify(parsed).replace(/["{}]/g, " ").trim();
    }
  } catch (e) {
    // Ignore parse errors, just return raw
  }
  return raw;
}

export function buildColumns(nowMs: number): TableColumn<QuarantineRow>[] {
  return [
    {
      key: "content",
      label: "Content",
      render: (r) => {
        const display = formatContent(r.content);
        return (
          <span className="block max-w-[320px] truncate text-ink" title={display}>
            {display}
          </span>
        );
      },
    },
    {
      key: "asset_id",
      label: "Asset",
      render: (r) =>
        r.asset_id ? (
          <Link
            href={`/assets/${r.asset_id}`}
            onClick={(e) => e.stopPropagation()}
            className="tabular text-accent hover:underline"
          >
            {r.asset_id}
          </Link>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      key: "input_type",
      label: "Type",
      render: (r) => <span className="text-muted">{triggerLabel(r.input_type)}</span>,
    },
    {
      key: "submitted_by",
      label: "Submitted by",
      render: (r) => <span className="text-muted">{r.submitted_by_name ?? r.submitted_by}</span>,
    },
    {
      key: "age",
      label: "Age",
      sortValue: (r) => Date.parse(r.submitted_at),
      render: (r) => <span className="tabular text-muted">{relativeTime(r.submitted_at)}</span>,
    },
    {
      key: "sla",
      label: "SLA",
      sortValue: (r) =>
        r.sla_due_at && r.review_status === "pending" ? Date.parse(r.sla_due_at) : Number.MAX_SAFE_INTEGER,
      render: (r) => <SlaChip item={r} nowMs={nowMs} />,
    },
    {
      key: "review_status",
      label: "Status",
      sortable: true,
      render: (r) => {
        const meta = STATUS_META[r.review_status] ?? STATUS_META.pending;
        return (
          <StatusBadge tone={meta.tone} pulse={r.review_status === "pending" && r.is_overdue}>
            {meta.label}
          </StatusBadge>
        );
      },
    },
  ];
}
