"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { QuarantineItem } from "@/lib/types";
import { relativeTime, triggerLabel } from "@/lib/utils";
import { Button, StatusBadge } from "@/components/ui";
import { SlaChip, formatContent } from "./columns";
import type { ActionMode } from "./actions";

const SESSION_TYPES = new Set(["elicitation_response", "offboarding_response", "voice_note"]);

const Meta = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div>
    <dt className="text-micro font-medium uppercase tracking-[0.06em] text-muted">{label}</dt>
    <dd className="mt-1 text-sm font-medium text-ink">{children}</dd>
  </div>
);

function SessionContext({ ctx, inputType }: { ctx: Record<string, unknown>; inputType: string }) {
  const [open, setOpen] = useState(false);
  if (!SESSION_TYPES.has(inputType)) return null;
  const entries = Object.entries(ctx);
  if (entries.length === 0) return null;

  return (
    <div className="rounded-xl border border-line bg-surface-2 text-sm overflow-hidden transition-colors hover:border-line-heavy">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-4 py-3 font-medium text-ink outline-none focus-visible:bg-surface-3"
      >
        <span>Session context <span className="ml-1 text-muted font-normal">({entries.length} field{entries.length !== 1 ? "s" : ""})</span></span>
        <svg
          width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          className={`text-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="space-y-3 border-t border-line px-4 pb-4 pt-3">
          {entries.map(([k, v]) => (
            <div key={k}>
              <span className="block text-micro font-medium uppercase tracking-[0.06em] text-muted">
                {k.replace(/_/g, " ")}
              </span>
              <span className="mt-1 block break-words text-sm text-ink font-mono bg-surface-3 px-2 py-1.5 rounded-md">
                {typeof v === "object" ? JSON.stringify(v, null, 2) : String(v ?? "—")}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Right slide-in detail panel. Esc + backdrop close, focus returns to the
 *  trigger. Action buttons hand off to the existing Modal flows via onAction. */
export function ItemPanel({
  item,
  nowMs,
  canPromote,
  canResolveDeviation = false,
  busy,
  escDisabled = false,
  onClose,
  onAction,
}: {
  item: QuarantineItem;
  nowMs: number;
  canPromote: boolean;
  /** Engineer/admin — matches `require_role` on POST /events/deviation-flag/{id}/resolve. */
  canResolveDeviation?: boolean;
  busy: boolean;
  /** Suspends the Esc handler while an action Modal is stacked on top. */
  escDisabled?: boolean;
  onClose: () => void;
  onAction: (mode: ActionMode) => void;
}) {
  const panelRef = useRef<HTMLElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => previouslyFocused.current?.focus?.();
  }, []);

  useEffect(() => {
    if (escDisabled) return;
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [escDisabled, onClose]);

  const pending = item.review_status === "pending";

  return (
    <div className="fixed inset-0 z-[100]" role="dialog" aria-modal="true" aria-label={`Quarantine item ${item.item_id}`}>
      <button
        type="button"
        className="absolute inset-0 animate-[overlay-in_150ms_ease-out] bg-[var(--scrim)]"
        aria-label="Close panel"
        onClick={onClose}
      />
      <aside
        ref={panelRef}
        tabIndex={-1}
        data-testid="quarantine-panel"
        className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col animate-[panel-in_250ms_ease-out] border-l border-line bg-surface shadow-2xl outline-none"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-4 top-4 z-10 grid size-8 place-items-center rounded-full bg-surface-2 text-muted transition-colors hover:bg-surface-3 hover:text-ink"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>

        <div className="flex-1 overflow-y-auto overscroll-contain px-6 py-6 pb-24">
          <header className="flex flex-col gap-4 border-b border-line pb-6">
            <h2 className="pr-10 text-xl font-semibold leading-tight text-ink text-balance break-words">
              {formatContent(item.content) || triggerLabel(item.input_type)}
            </h2>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone={pending ? "caution" : item.review_status === "promoted" ? "verified" : "danger"}>
                {pending ? "Unverified" : item.review_status === "promoted" ? "Promoted" : "Disputed"}
              </StatusBadge>
              <span className="text-sm font-medium text-muted">{triggerLabel(item.input_type)}</span>
              <SlaChip item={item} nowMs={nowMs} />
            </div>
          </header>

          <div className="mt-6 space-y-6">
            <div className="rounded-xl border border-line bg-surface-2 p-5">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-5">
                <Meta label="Asset">
                  {item.asset_id ? (
                    <Link href={`/assets/${item.asset_id}`} className="font-mono text-accent hover:underline">
                      {item.asset_id}
                    </Link>
                  ) : "—"}
                </Meta>
                <Meta label="Work order"><span className="font-mono">{item.work_order_id ?? "—"}</span></Meta>
                <Meta label="Submitted by">{item.submitted_by_name ?? item.submitted_by}</Meta>
                <Meta label="Submitted"><span className="tabular-nums">{relativeTime(item.submitted_at)}</span></Meta>
                <Meta label="Reviewer">{item.reviewer_name ?? item.reviewer_id ?? "—"}</Meta>
              </dl>
            </div>

            {item.session_context && <SessionContext ctx={item.session_context} inputType={item.input_type} />}

            {item.input_type === "deviation_flag" && pending && (
              <div className="flex items-start gap-3 rounded-xl border border-danger/20 bg-danger/5 px-4 py-3">
                <svg className="mt-0.5 shrink-0 text-danger" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-danger">Deviation flag</p>
                  {/* This used to send reviewers to the conflicts queue, which cannot resolve a deviation —
                      so a flagged asset's briefs stayed frozen with no way out of the UI. */}
                  <p className="text-sm leading-relaxed text-danger/80">
                    {canResolveDeviation
                      ? "Briefs for this asset are frozen until an engineer confirms or dismisses the flag."
                      : "Briefs for this asset are frozen until an engineer or admin resolves this flag."}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        <footer className="absolute bottom-0 left-0 right-0 border-t border-line bg-surface/90 px-6 py-4 pb-safe backdrop-blur-md">
          {pending ? (
            <div className="flex flex-col gap-3">
              {/* In the sticky footer with the other decisions — placed in the scrolling body it sat under
                  this footer and could not be reached without scrolling first. */}
              {item.input_type === "deviation_flag" && canResolveDeviation && (
                <Button className="w-full min-h-10" variant="primary" onClick={() => onAction("resolve-deviation")} disabled={busy}>
                  Resolve deviation
                </Button>
              )}
              <div className="flex items-center gap-3">
                {canPromote && (
                  <Button className="flex-1 min-h-10" variant="primary" onClick={() => onAction("promote")} disabled={busy}>
                    Promote
                  </Button>
                )}
                <Button className="flex-1 min-h-10" variant="ghost" onClick={() => onAction("dispute")} disabled={busy}>
                  Dispute
                </Button>
              </div>
              <Button className="w-full min-h-10 border border-line" variant="ghost" onClick={() => onAction("request-info")} disabled={busy}>
                Request additional info
              </Button>
              {!canPromote && (
                <p className="text-center text-xs text-muted">Promotion requires the reliability or admin role.</p>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center py-2">
              <span className={`inline-flex items-center gap-2 text-sm font-medium ${item.review_status === "promoted" ? "text-verified" : "text-danger"}`}>
                <span className={`size-2 rounded-full ${item.review_status === "promoted" ? "bg-verified" : "bg-danger"}`} aria-hidden="true" />
                {item.review_status === "promoted" ? "Promoted to canonical graph" : "Disputed"}
              </span>
            </div>
          )}
        </footer>
      </aside>
    </div>
  );
}
