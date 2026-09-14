"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { PlantOperatingState, PlantState } from "@/lib/types";
import { getPlantState, setPlantState } from "@/lib/api";
import { getMe } from "@/lib/auth";
import { ADMIN_ROLES } from "@/components/use-role";
import { Modal, StatusBadge, Button, PageHeader } from "@/components/ui";
import { fmtRelTime } from "@/lib/format";
import { STATE_META, STATES, toneToken } from "./_components/state-meta";

export default function PlantStatePage() {
  const [current, setCurrent] = useState<PlantState | null>(null);
  const [siteId, setSiteId] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<PlantOperatingState | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    let alive = true;
    getMe().then((u) => {
      if (!alive || !u) return;
      setSiteId(u.site_id);
      setIsAdmin(ADMIN_ROLES.includes(u.role));
      // Returned, not fire-and-forget: `getPlantState` now throws on failure instead of
      // returning a fixture, and an unreturned inner promise would reject outside the
      // outer .catch() — an unhandled rejection with the page stuck on its loading state.
      return getPlantState(u.site_id).then(({ data }) => {
        if (!alive) return;
        setFailed(false);
        setCurrent(data);
      });
    }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [reload]);

  async function handleConfirm() {
    if (!selected || !siteId) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await setPlantState({ site_id: siteId, state: selected });
      setCurrent(updated);
      setSuccess(true);
      setConfirming(false);
    } catch {
      setError("Failed to update plant state — backend offline or permission denied.");
    } finally {
      setBusy(false);
    }
  }

  const activeMeta = current ? STATE_META[current.state] : null;

  return (
    <div data-testid="plant-state-workspace" className="mx-auto max-w-[1200px]">
      <Link href="/management" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Overview
      </Link>

      <PageHeader className="mt-4" eyebrow="Plant control" title="Plant operating state" lede="Sets the operating mode for the whole site. Affects brief cadence, governor ceilings, and automation behaviour. Changes are logged and irreversible without an explicit transition." />

      <div data-testid="plant-state-layout" className="mt-5 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <main data-testid="plant-state-control" className="min-w-0 space-y-5">
      {/* Current state — tone-coded banner */}
      <section
        className="rounded-xl border border-line bg-surface p-5 shadow-sm"
        style={activeMeta ? {
          borderColor: `color-mix(in srgb, var(--${toneToken(activeMeta.tone)}) 35%, var(--line))`,
          backgroundColor: `color-mix(in srgb, var(--${toneToken(activeMeta.tone)}) 5%, var(--surface))`,
        } : undefined}
      >
        <p className="text-label font-bold uppercase tracking-[0.1em] text-muted">Current state</p>
        {current ? (
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            <StatusBadge tone={activeMeta!.tone}>{activeMeta!.label}</StatusBadge>
            <span className="text-body text-ink">{activeMeta!.desc}</span>
            <span className="tabular ml-auto text-label text-muted">
              {current.set_by && current.set_at
                ? `Set by ${current.set_by} · ${fmtRelTime(current.set_at)}`
                : "Site default"}
            </span>
          </div>
        ) : failed ? (
          <div className="mt-3 flex items-center gap-3">
            <span className="text-body text-muted">Couldn&apos;t load the current state.</span>
            <button type="button" onClick={() => setReload((r) => r + 1)} className="text-caption font-medium text-accent hover:underline">Retry</button>
          </div>
        ) : (
          <div className="mt-3 flex items-center gap-2">
            <span className="inline-flex gap-1.5">{[0,1,2].map((i) => <span key={i} className="size-2 animate-bounce rounded-full bg-muted" style={{ animationDelay: `${i * 0.15}s` }} />)}</span>
          </div>
        )}
      </section>

      {/* State selector — admin only */}
      {!isAdmin && (
        <div className="rounded-xl border border-line bg-surface p-5 text-body text-muted shadow-sm">
          Plant state changes require the <span className="font-semibold text-ink">admin</span> role.
          Contact your site administrator to request a state transition.
        </div>
      )}

      {isAdmin && (
        <section className="rounded-xl border border-line bg-surface p-5 shadow-sm">
          <p className="text-label font-bold uppercase tracking-[0.1em] text-muted">Transition to</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {STATES.map((s) => {
              const m = STATE_META[s];
              const isCurrent = current?.state === s;
              const isSelected = selected === s;
              return (
                <button
                  key={s}
                  onClick={() => { setSelected(s); setSuccess(false); }}
                  disabled={isCurrent}
                  aria-pressed={isSelected}
                  className={[
                    "min-h-[96px] rounded-xl border p-4 text-left transition-colors",
                    isCurrent
                      ? "cursor-default border-line bg-surface-2 opacity-50"
                      : isSelected
                      ? "border-accent bg-[color-mix(in_srgb,var(--accent)_8%,var(--surface))]"
                      : "border-line bg-surface hover:border-[color-mix(in_srgb,var(--accent)_40%,var(--line))]",
                  ].join(" ")}
                >
                  <div className="flex items-center gap-2">
                    <StatusBadge tone={m.tone}>{m.label}</StatusBadge>
                    {isCurrent && <span className="text-micro text-muted">(current)</span>}
                  </div>
                  <p className="mt-1.5 text-caption leading-snug text-muted">{m.desc}</p>
                </button>
              );
            })}
          </div>

          {selected && selected !== current?.state && (
            <div className="mt-4 flex items-center gap-3">
              <Button
                variant="danger"
                onClick={() => { setConfirming(true); setError(null); }}
              >
                Set to {STATE_META[selected].label}
              </Button>
              <button
                onClick={() => { setSelected(null); setSuccess(false); }}
                className="min-h-11 px-3 text-body text-muted hover:text-ink"
              >
                Cancel
              </button>
            </div>
          )}

          {success && (
            <p className="mt-3 text-body text-verified">
              State updated to <span className="font-semibold">{current ? STATE_META[current.state].label : "—"}</span>. Change logged.
            </p>
          )}
          {error && <p className="mt-3 text-body text-danger">{error}</p>}
        </section>
      )}
        </main>

        <aside data-testid="plant-state-context" className="rounded-xl border border-line bg-surface p-4 shadow-sm lg:sticky lg:top-20">
          <p className="text-label font-bold uppercase tracking-[0.1em] text-accent">Site scope</p>
          <p className="tabular mt-1 text-title font-semibold">{siteId ?? "Loading…"}</p>
          <div className="mt-4 border-t border-line pt-4">
            <p className="text-label font-semibold text-ink">Operational impact</p>
            <p className="mt-1.5 text-caption leading-relaxed text-muted">A transition immediately changes brief cadence, governor ceilings, and eligible automation for every user at this site.</p>
          </div>
          <div className="mt-4 border-t border-line pt-4">
            <p className="text-label font-semibold text-ink">Audit trail</p>
            <p className="mt-1.5 text-caption leading-relaxed text-muted">Every state change records the responsible user and timestamp. Reversal requires another explicit transition.</p>
          </div>
        </aside>
      </div>

      {/* Confirm modal */}
      {confirming && selected && (
        <Modal title={`Confirm: set to ${STATE_META[selected].label}`} onClose={() => setConfirming(false)}>
          <p className="text-body text-muted leading-relaxed">
            This will immediately transition <span className="font-semibold text-ink">{siteId}</span> to{" "}
            <span className="font-semibold" style={{ color: `var(--${toneToken(STATE_META[selected].tone)})` }}>
              {STATE_META[selected].label}
            </span>{" "}
            mode. The transition is logged and visible to all site users. Are you sure?
          </p>
          <div className="mt-5 flex gap-2">
            <Button variant="danger" disabled={busy} onClick={handleConfirm}>
              {busy ? "Updating…" : `Confirm — ${STATE_META[selected].label}`}
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(false)}>Cancel</Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
