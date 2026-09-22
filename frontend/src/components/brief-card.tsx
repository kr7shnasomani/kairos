import Link from "next/link";
import type { Brief } from "@/lib/types";
import { cn, priorityMeta, relativeTime, triggerLabel } from "@/lib/utils";
import { AuthorityBadge, StatusBadge } from "./ui";

import { Icon } from "@/components/icon";
/** A single brief in the inbox — priority left stripe, PTW/frozen states prominent. */
export function BriefCard({ brief }: { brief: Brief }) {
  const p = priorityMeta(brief.priority);
  const isFrozen = brief.frozen || brief.delivery_frozen;
  const topAuthority = brief.sources.reduce<number>((min, s) => Math.min(min, s.authority_level), 5) as 1|2|3|4|5;
  const quarantineCount = brief.sources.filter((s) => s.is_quarantine).length;

  return (
    <Link
      href={`/briefs/${brief.brief_id}`}
      className={cn(
        "group grid grid-cols-[4px_1fr] overflow-hidden rounded-xl border transition-colors",
        isFrozen
          ? "border-[color-mix(in_srgb,var(--info)_35%,var(--line))] bg-[color-mix(in_srgb,var(--info)_5%,var(--surface))] opacity-80"
          : "border-line bg-surface hover:border-[color-mix(in_srgb,var(--accent)_40%,var(--line))]",
        brief.acknowledged_at && "opacity-60",
      )}
    >
      <span
        aria-hidden="true"
        style={{ background: isFrozen ? "var(--info)" : p.color }}
        className={isFrozen ? "opacity-50" : ""}
      />
      <div className="flex flex-col gap-2 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {isFrozen ? (
              <span className="inline-flex items-center gap-1.5 text-label font-bold uppercase tracking-[0.1em] text-info">
                <Icon name="lock-simple" className="size-3" />
                Frozen
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-label font-bold uppercase tracking-[0.1em]" style={{ color: p.color }}>
                <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
                {brief.requires_countersignature ? "PTW-critical" : p.label}
              </span>
            )}
            <span className="text-label text-muted">· {triggerLabel(brief.trigger_event_type)}</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {brief.acknowledged_at && (
              <Icon name="check" className="size-3.5 text-verified" aria-label="Acknowledged" />
            )}
            <span className="tabular text-label text-muted">{relativeTime(brief.delivered_at)}</span>
          </div>
        </div>

        <h3 className={cn("text-subtitle font-semibold leading-snug text-ink", isFrozen && "text-muted")}>{brief.headline}</h3>

        {isFrozen && brief.freeze_reason ? (
          <p className="text-caption text-muted">
            Frozen: {brief.freeze_reason}
            {brief.freeze_deviation_flag_id && (
              <span className="ml-1 text-info"> — deviation flag pending resolution</span>
            )}
          </p>
        ) : (
          <p className="line-clamp-2 text-body leading-relaxed text-muted">{brief.body}</p>
        )}

        <div className="mt-0.5 flex flex-wrap items-center gap-2">
          <span className="text-label text-muted">{brief.sources.length} source{brief.sources.length !== 1 ? "s" : ""}</span>
          <AuthorityBadge level={topAuthority} />
          {brief.requires_countersignature && !isFrozen && <StatusBadge tone="danger">Countersignature</StatusBadge>}
          {quarantineCount > 0 && <StatusBadge tone="caution">{quarantineCount} unverified</StatusBadge>}
        </div>
      </div>
    </Link>
  );
}
