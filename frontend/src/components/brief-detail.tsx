// Brief detail — full brief view with provenance, PTW countersignature, ack and feedback flows.
"use client";

import Link from "next/link";
import { useState } from "react";
import type { Brief } from "@/lib/types";
import { priorityMeta, relativeTime, triggerLabel } from "@/lib/utils";
import { ackBrief, countersignBrief, sendBriefFeedback } from "@/lib/api";
import { PROMOTE_ROLES, useMe } from "./use-role";
import { AuthorityBadge, Button, EvidenceLineage, PageHeader, SourceChip, StatusBadge } from "./ui";

type FeedbackRating = "accurate" | "missing_context" | "incorrect";
type AckStep = "idle" | "step1_done" | "complete";

export function BriefDetail({ brief }: { brief: Brief }) {
  const p = priorityMeta(brief.priority);
  const isPtw = brief.requires_countersignature;
  const me = useMe();

  // Server truth, not local step state: a PTW brief's two signatures are made by two different
  // people in two different sessions, so step 2 has to be driven by what the backend recorded.
  const ackedBy = brief.acknowledged_by ?? null;
  const counterBy = brief.countersigned_by ?? null;
  const canCountersign =
    isPtw &&
    !!ackedBy &&
    !counterBy &&
    !!me &&
    PROMOTE_ROLES.includes(me.role) &&
    me.user_id !== ackedBy;
  // Only the brief's addressee (the user, or their whole site for site-wide briefs) can give the first
  // signature — the API scopes /ack to recipients. Staff may still OPEN someone else's PTW brief to
  // countersign it, and used to be offered a signature box whose submit 404'd as "check your connection".
  const isRecipient =
    !!me && (brief.recipient_user_id === me.user_id || brief.recipient_user_id === `site-${me.site_id}`);
  const isFrozen = brief.frozen || brief.delivery_frozen;
  const quarantineCount = brief.sources.filter((s) => s.is_quarantine).length;
  const hasLowConfidence = quarantineCount > 0;

  const [ackStep, setAckStep] = useState<AckStep>("idle");
  const [engineerSig, setEngineerSig] = useState("");
  const [ackBusy, setAckBusy] = useState(false);
  const [ackError, setAckError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<FeedbackRating | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);

  /** Signature 1 — the issuing authority. Always hits the API, for PTW briefs too: the
   *  engineer's acknowledgment is what the countersignature is later checked against. */
  async function ackStep1() {
    if (engineerSig.trim().length < 2 || ackBusy) return;
    setAckBusy(true);
    setAckError(null);
    try {
      await ackBrief(brief.brief_id, { signature: engineerSig });
      // PTW is not delivered on one signature — it now waits for a second authority.
      setAckStep(isPtw ? "step1_done" : "complete");
    } catch {
      setAckError("Acknowledgment failed to save — check your connection and try again.");
    } finally {
      setAckBusy(false);
    }
  }

  /** Signature 2 — a different authenticated person holding reliability/admin. Identity comes
   *  from the session, never a typed name, which is what makes the audit trail meaningful. */
  async function ackStep2() {
    if (ackBusy || !canCountersign) return;
    setAckBusy(true);
    setAckError(null);
    try {
      await countersignBrief(brief.brief_id);
      setAckStep("complete");
    } catch {
      setAckError("Countersignature failed to save — the brief is not yet delivered. Try again.");
    } finally {
      setAckBusy(false);
    }
  }

  async function rate(r: FeedbackRating) {
    setFeedback(r);
    setFeedbackError(null);
    setFeedbackBusy(true);
    try {
      await sendBriefFeedback(brief.brief_id, r);
      setFeedbackSent(true);
    } catch {
      setFeedback(null);
      setFeedbackError("Feedback failed to send — try again.");
    } finally {
      setFeedbackBusy(false);
    }
  }

  // Complete on server truth as well as local state, so reopening a signed brief in a fresh
  // session shows it signed. PTW needs both signatures; everything else needs one.
  const isComplete =
    ackStep === "complete" || (isPtw ? !!counterBy : !!brief.acknowledged_at);
  // PTW awaiting its second signature — the state the old UI could never leave.
  const awaitingCountersign = isPtw && !!ackedBy && !counterBy && !isComplete;

  return (
    <div data-testid="brief-detail-workspace" className="mx-auto max-w-[1400px]">
      <Link href="/briefs" className="inline-flex items-center gap-1.5 text-body text-muted hover:text-ink">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Briefs
      </Link>

      {/* Badge row stays above the PageHeader; outer div avoids nested <header> elements. */}
      <div className="mt-4">
        <div className="flex flex-wrap items-center gap-2">
          {isFrozen ? (
            <StatusBadge tone="info">Frozen</StatusBadge>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-label font-bold uppercase tracking-[0.1em]" style={{ color: p.color }}>
              <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
              {isPtw ? "PTW-critical" : p.label}
            </span>
          )}
          <span className="text-label text-muted">· {triggerLabel(brief.trigger_event_type)}</span>
          <span className="tabular ml-auto text-label text-muted">{relativeTime(brief.delivered_at)}</span>
        </div>
        <PageHeader compact className="mt-1" title={brief.headline} />
        {isPtw && (
          <div className="mt-2 flex flex-wrap gap-2">
            <StatusBadge tone="danger">Permit-to-Work — dual countersignature required</StatusBadge>
          </div>
        )}
      </div>

      {/* Frozen state explanation */}
      {isFrozen && (
        <div className="mt-4 rounded-xl border border-[color-mix(in_srgb,var(--info)_30%,var(--line))] bg-[color-mix(in_srgb,var(--info)_7%,transparent)] p-4">
          <p className="text-body font-semibold text-info">Delivery frozen</p>
          <p className="mt-1 text-caption text-muted">
            {brief.freeze_reason ?? "A physical deviation flag is pending resolution."}
            {" "}Briefs for this asset are held until an engineer resolves the flag.
          </p>
        </div>
      )}

      {/* Unverified field input warning */}
      {hasLowConfidence && (
        <div className="mt-4 rounded-xl border border-[color-mix(in_srgb,var(--caution)_35%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_8%,transparent)] p-3">
          <p className="text-caption font-semibold text-caution">
            Draws on unverified field input — {quarantineCount} source{quarantineCount !== 1 ? "s" : ""} not reviewed by engineering authority
          </p>
        </div>
      )}

      <div data-testid="brief-detail-layout" className="mt-5 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <main data-testid="brief-content" className="min-w-0">
      <p className="text-sm leading-relaxed text-ink/90">{brief.body}</p>

      {brief.warnings.length > 0 && (
        <div className="mt-5 rounded-xl border border-[color-mix(in_srgb,var(--caution)_35%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_9%,var(--surface))] p-4">
          <p className="text-label font-bold uppercase tracking-[0.1em] text-caution">Warnings</p>
          <ul className="mt-2 space-y-1.5">
            {brief.warnings.map((w) => (
              <li key={w} className="flex gap-2 text-body text-ink">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-caution" aria-hidden="true" />
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}

      {brief.action_items.length > 0 && (
        <section className="mt-6">
          <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">
            {isPtw ? "Isolation sequence / actions" : "What to do"}
          </h2>
          <ul className="mt-3 space-y-2">
            {brief.action_items.map((a) => (
              <li key={a} className="flex items-start gap-2.5 rounded-lg border border-line bg-surface px-3.5 py-2.5 text-body">
                <svg className="mt-0.5 size-4 shrink-0 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
                {a}
              </li>
            ))}
          </ul>
        </section>
      )}

        </main>

        <aside data-testid="brief-context" className="min-w-0 space-y-5">

      {/* Evidence */}
      <section>
        <h2 className="text-xs font-bold uppercase tracking-[0.1em] text-muted">Evidence</h2>
        <div className="mt-3 space-y-2.5">
          {/* One document can back several sources (distinct chunks), so the id alone is not a unique key. */}
          {brief.sources.map((s, i) => (
            <article key={`${s.document_id}-${i}`} className="rounded-xl border border-line bg-surface p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-body font-semibold">{s.title}</span>
                <AuthorityBadge level={s.authority_level} />
                {s.is_quarantine && (
                  <StatusBadge tone="caution" dot={false}>Unverified field input — not reviewed by engineering authority</StatusBadge>
                )}
              </div>
              <p className="mt-2 text-body leading-relaxed text-muted">{s.relevant_excerpt}</p>
              <div className="mt-2.5 flex items-center gap-2">
                <SourceChip quarantine={s.is_quarantine}>{s.document_id}</SourceChip>
                {s.vault_url && (
                  <a href={s.vault_url} target="_blank" rel="noreferrer" className="text-caption font-medium text-accent hover:underline">
                    Open in vault →
                  </a>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* Safety refusal — if all sources are quarantine + no verified evidence */}
      {/* Evidence lineage */}
      <div>
        <EvidenceLineage sources={brief.sources} />
      </div>

      {/* PTW dual sign-off or standard ack */}
      <section data-testid="brief-acknowledgment" className="rounded-xl border border-line bg-surface p-5 shadow-sm lg:sticky lg:top-20" aria-label="Acknowledgment">
        {isComplete ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-body font-semibold text-verified">
              <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M20 6 9 17l-5-5" />
              </svg>
              {isPtw
                ? `PTW signed off — acknowledged by ${brief.acknowledged_by_name ?? (engineerSig || "engineer")} · countersigned by ${brief.countersigned_by_name ?? me?.email ?? "second authority"}`
                : `Acknowledged${engineerSig ? ` · signed ${engineerSig}` : ""}`}
            </div>
            <p className="text-caption text-muted">Both identities and timestamps are logged in the audit trail.</p>
          </div>
        ) : awaitingCountersign || (isPtw && ackStep === "step1_done") ? (
          /* Signature 2 — a second, distinct authority. Identity comes from their session. */
          <div data-testid="brief-countersign">
            <p className="text-body font-semibold">Step 2 of 2 — countersignature</p>
            <p className="mt-1 text-caption text-muted">
              Acknowledged by <span className="font-medium text-ink">{brief.acknowledged_by_name ?? (engineerSig || "the issuing engineer")}</span>. A
              second authority must confirm the isolation strategy before this permit is delivered.
            </p>
            {canCountersign ? (
              <>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button variant="primary" onClick={ackStep2} disabled={ackBusy}>
                    {ackBusy ? "Saving…" : "Countersign permit"}
                  </Button>
                  {/* Identity, not a raw uuid in the button label. */}
                  <span className="text-caption text-muted">
                    Signed as <span className="font-medium text-ink">{me!.email || me!.user_id}</span> — your session identity, not a typed name.
                  </span>
                </div>
                {ackError && <p className="mt-2 text-caption text-danger">{ackError}</p>}
              </>
            ) : (
              <p className="mt-3 rounded-lg border border-line bg-surface-2 px-3 py-2 text-caption text-muted">
                {me && me.user_id === ackedBy
                  ? "You acknowledged this brief. A countersignature has to come from someone else — that is the point of dual sign-off."
                  : "Waiting on a reliability engineer or administrator to countersign. Engineers cannot provide both signatures."}
              </p>
            )}
          </div>
        ) : (
          /* Step 1 (or single-step for non-PTW) */
          <div>
            <p className="text-caption text-muted">
              {isPtw
                ? "Step 1 of 2 — Issuing engineer acknowledges brief content and isolation strategy."
                : "Acknowledge receipt. Your signature is logged with the evidence lineage."}
            </p>
            {isRecipient ? (
              <input
                value={engineerSig}
                onChange={(e) => setEngineerSig(e.target.value)}
                placeholder={isPtw ? "Issuing engineer: type your name" : "Type your name to sign"}
                className="mt-3 min-h-11 w-full rounded-lg border border-line bg-surface-2 px-3 text-body outline-none focus-visible:border-accent"
                aria-label="Engineer signature"
              />
            ) : (
              <p className="mt-3 rounded-lg border border-line bg-surface-2 px-3 py-2 text-caption text-muted">
                Waiting on the brief&apos;s recipient to acknowledge it. The first signature can only come from the person it was issued to.
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-3">
              {isRecipient && (
                <Button
                  variant={isPtw ? "danger" : "primary"}
                  onClick={ackStep1}
                  disabled={engineerSig.trim().length < 2 || ackBusy}
                >
                  {ackBusy ? "Saving…" : isPtw ? "Acknowledge (step 1 of 2)" : "Acknowledge"}
                </Button>
              )}

              {/* Phase 2 feedback chips */}
              <div className="ml-auto flex items-center gap-1.5">
                <span className="text-caption text-muted">Accurate?</span>
                {(["accurate", "missing_context", "incorrect"] as FeedbackRating[]).map((r) => (
                  <button
                    key={r}
                    onClick={() => { if (!feedbackSent && !feedbackBusy) void rate(r); }}
                    disabled={feedbackSent || feedbackBusy}
                    className={`min-h-11 rounded-md border px-2 py-1 text-label font-medium capitalize transition-colors disabled:cursor-default ${
                      feedback === r
                        ? "border-accent text-accent"
                        : "border-line text-muted hover:text-ink"
                    }`}
                  >
                    {r.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>
            {ackError && <p className="mt-2 text-caption text-danger">{ackError}</p>}
            {feedbackSent && (
              <p className="mt-2 text-caption text-muted">
                Thanks — feedback recorded{feedback === "incorrect" ? "; source confidence recheck queued." : "."}
              </p>
            )}
            {feedbackError && <p className="mt-2 text-caption text-danger">{feedbackError}</p>}
          </div>
        )}
      </section>
        </aside>
      </div>
    </div>
  );
}
