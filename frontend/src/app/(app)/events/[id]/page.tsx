"use client";

// Operational event detail: payload, correlated events, acknowledge action.
import Link from "next/link";
import { use, useEffect, useState } from "react";
import type { OperationalEvent, EventPriority } from "@/lib/types";
import { getEvent, ackEvent } from "@/lib/api";
import { getMe } from "@/lib/auth";
import { Button, StatusBadge, EmptyState, PageHeader } from "@/components/ui";
import { DetailSkeleton } from "@/components/skeleton";
import { relativeTime, triggerLabel } from "@/lib/utils";

const PRIORITY_TONE: Record<EventPriority, "danger" | "caution" | "info" | "neutral"> = {
  critical: "danger", high: "caution", normal: "info", low: "neutral",
};

export default function EventDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [event, setEvent] = useState<OperationalEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [acking, setAcking] = useState(false);
  const [ackError, setAckError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getEvent(id).then(({ data }) => { if (alive) { setEvent(data); setLoading(false); } });
    return () => { alive = false; };
  }, [id]);

  async function handleAck() {
    setAcking(true);
    setAckError(null);
    try {
      const user = await getMe();
      if (!user) throw new Error("Sign in again before acknowledging this event.");
      await ackEvent(id, { user_id: user.user_id, role: user.role });
      setEvent((e) => e ? { ...e, acknowledged: true, acknowledged_by: user.user_id } : e);
    } catch (error) {
      setAckError(error instanceof Error ? error.message : "Could not acknowledge this event.");
    } finally {
      setAcking(false);
    }
  }

  return (
    <div data-testid="event-detail-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/events" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Events
      </Link>

      {loading && <div className="mt-6"><DetailSkeleton /></div>}

      {!loading && !event && (
        <div className="mt-6"><EmptyState message={`Event ${id} not found.`} action={{ label: "Back to events", href: "/events" }} /></div>
      )}

      {event && (
        <>
          <div data-testid="event-summary" className="mt-4 rounded-xl border border-line bg-surface px-4 py-5 shadow-sm sm:px-5">
            <PageHeader
              compact
              eyebrow={event.event_id}
              title={triggerLabel(event.event_type)}
              lede={
                <>
                  {event.asset_id && <span className="tabular text-accent">{event.asset_id}</span>}
                  {event.asset_id && " · "}
                  {relativeTime(event.occurred_at)}
                  {event.site_id && ` · ${event.site_id}`}
                </>
              }
              actions={
                <>
                  <StatusBadge tone={PRIORITY_TONE[event.priority]}>{event.priority}</StatusBadge>
                  {event.event_subtype === "recurring" && <StatusBadge tone="caution" dot={false}>recurring</StatusBadge>}
                  {event.acknowledged && <StatusBadge tone="verified">acknowledged</StatusBadge>}
                </>
              }
            />
          </div>

          <div data-testid="event-detail-columns" className="fluid-tile-pair mt-6">
            <main className="min-w-0 space-y-6">
              {event.brief_id && (
                <Link href={`/briefs/${event.brief_id}`} className="flex min-h-14 items-center justify-between gap-4 rounded-xl border border-line bg-surface px-4 py-3 text-body shadow-sm transition-colors hover:bg-surface-2 sm:px-5">
                  <span>Triggered brief <span className="tabular font-semibold text-accent">{event.brief_id}</span></span>
                  <span className="shrink-0 text-caption font-semibold text-accent">Open brief →</span>
                </Link>
              )}

              {/* A work order is where tacit knowledge gets captured (Layer 6): the micro-interview
                  and the voice note both key on its id, and nothing else in the app linked to them. */}
              {typeof event.payload.work_order_id === "string" && event.payload.work_order_id && (
                <section data-testid="work-order-capture" className="rounded-xl border border-line bg-surface px-4 py-4 shadow-sm sm:px-5">
                  <h2 className="text-sm font-semibold text-ink">Capture knowledge from <span className="tabular">{event.payload.work_order_id}</span></h2>
                  <p className="mt-0.5 text-caption text-muted">Answer the micro-interview or record a voice note. Both go to quarantine for engineering review.</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Link href={`/field/elicitation/${encodeURIComponent(event.payload.work_order_id)}`} className="inline-flex h-9 items-center rounded-lg bg-accent px-3.5 text-body font-semibold text-on-accent hover:brightness-105">Knowledge capture</Link>
                    <Link href={`/field/voice/${encodeURIComponent(event.payload.work_order_id)}`} className="inline-flex h-9 items-center rounded-lg border border-line px-3.5 text-body font-semibold text-ink hover:bg-surface-2">Voice note</Link>
                  </div>
                </section>
              )}

              <section className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
                <div className="border-b border-line px-4 py-4 sm:px-5">
                  <h2 className="text-sm font-semibold text-ink">Event payload</h2>
                  <p className="mt-0.5 text-caption text-muted">Operational values captured when this event occurred.</p>
                </div>
                {Object.keys(event.payload).length === 0 ? (
                  <p className="px-4 py-10 text-center text-body text-muted sm:px-5">No payload values recorded.</p>
                ) : (
                  <dl className="divide-y divide-line">
                    {Object.entries(event.payload).map(([key, value]) => {
                      const label = key.replaceAll("_", " ");
                      return (
                        <div key={key} className="grid gap-1 px-4 py-3.5 sm:grid-cols-[minmax(140px,0.35fr)_minmax(0,1fr)] sm:gap-4 sm:px-5">
                          <dt className="text-caption font-medium text-muted">{label.charAt(0).toUpperCase() + label.slice(1)}</dt>
                          <dd className="min-w-0 break-words text-caption font-medium text-ink">
                            {value == null ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value)}
                          </dd>
                        </div>
                      );
                    })}
                  </dl>
                )}
              </section>
            </main>

            <aside className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
              <div className="border-b border-line px-4 py-4 sm:px-5">
                <h2 className="text-sm font-semibold text-ink">Event details</h2>
                <p className="mt-0.5 text-caption text-muted">Source, timing, and review state.</p>
              </div>
              <dl className="divide-y divide-line px-4 sm:px-5">
                <div className="py-3.5">
                  <dt className="text-label text-muted">Asset</dt>
                  <dd className="tabular mt-1 text-caption font-semibold text-accent">{event.asset_id ?? "Site-wide"}</dd>
                </div>
                <div className="py-3.5">
                  <dt className="text-label text-muted">Subtype</dt>
                  <dd className="mt-1 text-caption font-medium capitalize text-ink">{event.event_subtype?.replaceAll("_", " ") ?? "—"}</dd>
                </div>
                <div className="py-3.5">
                  <dt className="text-label text-muted">Site</dt>
                  <dd className="tabular mt-1 text-caption font-medium text-ink">{event.site_id ?? "—"}</dd>
                </div>
                <div className="py-3.5">
                  <dt className="text-label text-muted">Occurred</dt>
                  <dd className="mt-1 text-caption font-medium text-ink">
                    <time dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleString()}</time>
                  </dd>
                </div>
              </dl>

              {(event.correlated_event_ids?.length ?? 0) > 0 && (
                <section className="border-t border-line px-4 py-4 sm:px-5">
                  <h3 className="text-label font-semibold text-muted">Correlated events</h3>
                  <ul className="mt-2 space-y-2">
                    {event.correlated_event_ids!.map((cid) => (
                      <li key={cid}>
                        <Link href={`/events/${cid}`} className="tabular inline-flex min-h-11 items-center text-caption font-semibold text-accent hover:underline sm:min-h-0">{cid} →</Link>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <div className="border-t border-line px-4 py-4 sm:px-5">
                {!event.acknowledged ? (
                  <Button className="h-11 w-full" variant="primary" onClick={handleAck} disabled={acking}>
                    {acking ? "Acknowledging…" : "Acknowledge event"}
                  </Button>
                ) : event.acknowledged_by ? (
                  <p className="text-caption text-verified">Acknowledged by <span className="font-semibold">{event.acknowledged_by}</span></p>
                ) : (
                  <StatusBadge tone="verified">acknowledged</StatusBadge>
                )}
                {ackError && <p role="alert" className="mt-2 text-caption text-danger">{ackError}</p>}
              </div>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
