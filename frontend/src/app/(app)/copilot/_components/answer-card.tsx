"use client";

import { useState } from "react";
import { getArtifactUrl, submitAnswerFeedback } from "@/lib/api";
import { META_MODEL, type CopilotAnswer } from "@/lib/copilot";
import { AuthorityBadge, SourceChip, StatusBadge, ConfidenceMeter } from "@/components/ui";
import { cn } from "@/lib/utils";
import { EntityAnnotations } from "./entity-annotations";

// Phase 1 = retrieval only (no synthesized prose); 2+ = full synthesis.
const PHASE = process.env.NEXT_PUBLIC_KAIROS_PHASE ?? "3";
export const SYNTHESIS_ENABLED = PHASE !== "1";

const SECTION_MARKERS = ["CONFIDENCE:", "UNCERTAINTY:", "SOURCES_USED:"];

/** Streamed text with the model's section scaffolding removed, for display while synthesis runs.
 *  The provider streams its raw `ANSWER: … CONFIDENCE: … SOURCES_USED: …` contract; the final
 *  answer is parsed server-side, so this only keeps markers — including one still half-arrived at
 *  the end of a chunk — from flashing on screen. Nothing after the first section marker is shown. */
export function provisionalText(raw: string): string {
  if ("ANSWER:".startsWith(raw.trim().toUpperCase())) return "";
  let body = raw.replace(/^\s*ANSWER:\s*/i, "");
  const cut = SECTION_MARKERS.map((m) => body.indexOf(m)).filter((i) => i >= 0);
  if (cut.length) body = body.slice(0, Math.min(...cut));
  const tail = body.match(/\s([A-Z_]{1,13}:?)$/);
  if (tail && SECTION_MARKERS.some((m) => m.startsWith(tail[1]))) body = body.slice(0, tail.index);
  return body.trimEnd();
}

export function Thinking() {
  return (
    <div className="flex items-center gap-2 text-body text-muted">
      <span className="inline-flex gap-1" aria-hidden="true">
        <span className="size-1.5 animate-bounce rounded-full bg-muted [animation-delay:-0.3s]" />
        <span className="size-1.5 animate-bounce rounded-full bg-muted [animation-delay:-0.15s]" />
        <span className="size-1.5 animate-bounce rounded-full bg-muted" />
      </span>
      Assembling evidence…
    </div>
  );
}

/** `vault_url` is Supabase's `/object/authenticated/` endpoint: a plain <a> click cannot send
 *  the Authorization header it requires, so the browser gets a 400 ("headers must have required
 *  property 'authorization'") rendered as a bare error page — confirmed live, not a real 404.
 *  Fetch a short-lived signed URL instead — the token rides in the query string, so a plain
 *  `window.open` works. Same contract as `documents-table.tsx`'s `DownloadCell` and
 *  `documents/[id]/open-artifact.tsx`; this component used to link `vault_url` directly and
 *  every "View file" click failed the same way every un-migrated Download link once did. */
function ViewFileLink({ documentId }: { documentId: string }) {
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  return (
    <button
      type="button"
      disabled={status === "loading"}
      onClick={async () => {
        setStatus("loading");
        const url = await getArtifactUrl(documentId);
        if (url) {
          setStatus("idle");
          window.open(url, "_blank", "noopener,noreferrer");
        } else {
          setStatus("error");
        }
      }}
      className="text-label text-accent underline hover:no-underline disabled:opacity-60"
    >
      {status === "loading" ? "Opening…" : status === "error" ? "Retry" : "View file ↗"}
    </button>
  );
}

/** Retrieval or synthesis failed. Shown instead of an answer — the copilot never
 *  substitutes fixture content for governed evidence. */
export function AnswerError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div data-testid="copilot-answer-error" role="alert" className="rounded-xl border border-line bg-surface p-4">
      <p className="text-body font-medium text-ink">No governed answer available.</p>
      <p className="mt-1 text-caption text-muted">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 inline-flex min-h-11 items-center rounded-lg border border-line bg-surface-2 px-4 text-caption font-medium text-ink transition-colors hover:bg-canvas"
      >
        Retry
      </button>
    </div>
  );
}

export function Answer({ data, query = "", streaming }: {
  data: CopilotAnswer;
  query?: string;
  /** Provisional text streamed so far. Rendered only while `data.is_synthesizing` — it has
   *  no sources or confidence yet and the safety gate may still refuse the whole answer. */
  streaming?: string;
}) {
  const [feedback, setFeedback] = useState<string | null>(null);
  const [feedbackFailed, setFeedbackFailed] = useState(false);
  // Collapsed by default — a multi-source answer used to dump every source card open,
  // pushing the confidence meter and feedback buttons below the fold.
  const [sourcesOpen, setSourcesOpen] = useState(false);

  // Phase-2 trust loop. These buttons used to set local state only, so the rating the
  // architecture calls "direct input to outcome attribution and Layer 0" went nowhere.
  async function rate(rating: "accurate" | "missing_context" | "incorrect") {
    setFeedback(rating);
    setFeedbackFailed(false);
    const ok = await submitAnswerFeedback({ query, rating, model: data.model });
    if (!ok) {
      // Never claim a save that did not happen — clear the selection and say so.
      setFeedback(null);
      setFeedbackFailed(true);
    }
  }

  const pendingMoc = data.pending_moc ?? [];

  const hasQuarantine = data.sources.some((s) => s.is_quarantine);
  // Non-safety, non-refused, low confidence — show uncertainty block.
  // `null` must NOT count as low: it means the model reported no confidence, and the old
  // `confidence < 0.7` on a null-coerced-to-0 fired this warning on ~23% of perfectly good
  // answers. Unknown gets no badge at all — the footer says it is unreported instead.
  const confidence = data.confidence;
  const uncertain = !data.refused && confidence !== null && confidence < 0.7;
  const confidencePct = confidence !== null ? Math.round(confidence * 100) : null;
  // A locally-answered meta question ("what can you do?"). It has no sources because it is
  // not retrieved knowledge, which would otherwise make it the one answer in the app without
  // provenance. Rendered as a labelled system reply so it cannot be read as a governed claim,
  // and without the feedback control — there is no retrieval quality to rate.
  const isMeta = data.model === META_MODEL;

  if (isMeta) {
    return (
      <div className="space-y-3 rounded-2xl rounded-bl-sm border border-line bg-surface-2 p-4">
        <div className="flex items-center gap-2">
          <StatusBadge tone="neutral">About Kairos</StatusBadge>
          <span className="text-caption text-muted">Not a knowledge answer — no sources cited</span>
        </div>
        <div className="space-y-2 text-sm leading-relaxed text-ink">
          {(data.answer ?? "").split("\n").map((line, i) =>
            line.trim() === "" ? null : (
              <p key={i} className={line.startsWith("**") ? "font-semibold text-ink" : "text-pretty"}>
                {line.replace(/\*\*/g, "")}
              </p>
            ),
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3.5 rounded-2xl rounded-bl-sm border border-line bg-surface p-4">
      {/* Pending-MoC banner. Architecture Layer 7 / Flow C: while an engineering conflict is in
          the MoC queue the canonical graph is deliberately NOT updated, so this answer may be
          reporting a value that is under formal dispute. Rendered ABOVE the answer — after it,
          a technician has already read and acted on the number. */}
      {pendingMoc.length > 0 && (
        <div
          role="alert"
          data-testid="pending-moc-banner"
          className="rounded-lg border border-[color-mix(in_srgb,var(--caution)_45%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_10%,var(--surface))] px-3 py-2.5 text-caption text-caution"
        >
          <p className="font-semibold">
            Change under review — {pendingMoc.length === 1 ? "a parameter" : "parameters"} in this
            answer {pendingMoc.length === 1 ? "is" : "are"} awaiting Management of Change sign-off.
          </p>
          <ul className="mt-1.5 space-y-0.5">
            {pendingMoc.map((m) => (
              <li key={m.conflict_id} className="tabular">
                {m.moc_id ?? "MoC pending assignment"} — {m.parameter} on {m.asset_id}
                {m.moc_status ? ` (${m.moc_status.replace(/_/g, " ")})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Quarantine dependency banner */}
      {hasQuarantine && (
        <div className="flex items-center gap-2 rounded-lg border border-[color-mix(in_srgb,var(--caution)_35%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_8%,var(--surface))] px-3 py-2 text-caption text-caution">
          <svg
            className="size-3.5 shrink-0"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          Draws on unverified field input — treat with additional caution
        </div>
      )}

      {/* Safety-critical refusal — no synthesized prose, sources returned directly */}
      {data.refused ? (
        <div
          role="alert"
          className="rounded-lg border border-[color-mix(in_srgb,var(--danger)_35%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_8%,var(--surface))] p-3.5"
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
              <p className="text-body font-semibold text-danger">
                Safety-critical query — refused
              </p>
              {data.refusal_reason && (
                <p className="mt-1 text-caption leading-relaxed text-muted">
                  {data.refusal_reason}
                </p>
              )}
              <p className="mt-2 text-caption text-muted">
                Confirm the value directly with the responsible engineer before acting.
              </p>
            </div>
          </div>
        </div>
      ) : data.is_synthesizing ? (
        /* Streamed text while synthesis is still running. Deliberately styled as in-progress,
           not as an answer: the safety gate can still replace the whole thing with a refusal,
           and it carries no sources or confidence yet. Safety-critical categories never stream,
           so this branch shows the plain spinner for exactly the queries where a provisional
           claim would be most dangerous. */
        streaming ? (
          <div aria-live="polite" aria-busy="true">
            <p className="whitespace-pre-wrap text-body text-ink/85">
              {provisionalText(streaming)}
              <span className="ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-pulse rounded-sm bg-accent align-baseline" aria-hidden="true" />
            </p>
            <p className="mt-2 text-caption text-muted">
              Synthesizing — sources and confidence are attached once the answer is complete.
            </p>
          </div>
        ) : (
          <Thinking />
        )
      ) : uncertain ? (
        /* Non-safety uncertainty: show answer but call out low evidence */
        <div className="rounded-lg border border-[color-mix(in_srgb,var(--caution)_35%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_6%,var(--surface))] p-3.5">
          <div className="mb-2 flex items-center gap-2">
            <StatusBadge tone="caution">
              Low confidence · {confidencePct}%
            </StatusBadge>
          </div>
          {SYNTHESIS_ENABLED && data.answer && (
            <p className="text-sm leading-relaxed text-ink text-pretty">{data.answer}</p>
          )}
          <p className="mt-2 border-t border-[color-mix(in_srgb,var(--caution)_20%,var(--line))] pt-2 text-caption leading-relaxed text-muted">
            Evidence below 70% threshold — verify directly against the sources below before acting.
            Escalate to the responsible engineer for any safety-affecting decision.
          </p>
        </div>
      ) : SYNTHESIS_ENABLED ? (
        <p className="text-sm leading-relaxed text-ink text-pretty">{data.answer}</p>
      ) : (
        /* Phase 1 gate — retrieval only */
        <div className="flex items-center gap-2 rounded-lg border border-[color-mix(in_srgb,var(--caution)_30%,var(--line))] bg-[color-mix(in_srgb,var(--caution)_6%,var(--surface))] px-3 py-2.5 text-caption text-caution">
          <span className="size-1.5 shrink-0 rounded-full bg-caution" aria-hidden="true" />
          Phase 1 — source documents returned directly. Synthesis activates in Phase 2.
        </div>
      )}

      {/* Sources with authority + quarantine badges. Gated on !is_synthesizing like the
          footer below — `onSources` delivers a partial CopilotAnswer with sources already
          populated the moment retrieval finishes, well before the answer text is ready, so
          without this gate the source cards appeared first and the answer visibly caught up
          to them afterward. */}
      {!data.is_synthesizing && data.sources.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setSourcesOpen((v) => !v)}
            aria-expanded={sourcesOpen}
            className="flex w-full items-center gap-1.5 text-micro font-bold uppercase tracking-[0.1em] text-muted hover:text-ink"
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={cn("shrink-0 transition-transform", sourcesOpen && "rotate-90")}
              aria-hidden="true"
            >
              <path d="M9 6l6 6-6 6" />
            </svg>
            {data.refused ? "Sources — verify directly" : "Sources"} · {data.sources.length}
          </button>
          {sourcesOpen && (
          <div className="mt-2 space-y-2">
            {data.sources.map((s) => (
              <div
                key={s.document_id}
                className="flex flex-col gap-1.5 rounded-lg border border-line bg-surface-2 p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-body font-semibold">{s.title}</span>
                  <AuthorityBadge level={s.authority_level} />
                  {s.is_quarantine && <StatusBadge tone="caution">Unverified</StatusBadge>}
                </div>
                {s.excerpt && (
                  <p className="text-caption leading-relaxed text-muted">{s.excerpt}</p>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <SourceChip quarantine={s.is_quarantine}>{s.document_id}</SourceChip>
                  {s.vault_url && <ViewFileLink documentId={s.document_id} />}
                </div>
              </div>
            ))}
          </div>
          )}
        </div>
      )}

      {/* Entity annotation chips */}
      {!data.is_synthesizing && data.entities && data.entities.length > 0 && (
        <EntityAnnotations entities={data.entities} />
      )}

      {/* Footer: confidence meter + model + feedback */}
      {!data.refused && !data.is_synthesizing && (
        <div className="space-y-2.5 border-t border-line pt-3">
          <ConfidenceMeter value={data.confidence} />
          <div className="flex items-center gap-3 text-label text-muted">
            {data.model && (
              <span className="max-w-[200px] truncate tabular">{data.model}</span>
            )}
            <div className="ml-auto flex items-center gap-1.5">
              {feedbackFailed && (
                <span role="status" className="text-label text-caution">
                  Rating not saved
                </span>
              )}
              {(["accurate", "missing_context", "incorrect"] as const).map((r) => (
                <button
                  key={r}
                  onClick={() => void rate(r)}
                  aria-pressed={feedback === r}
                  className={cn(
                    "rounded-md border px-2 py-1 text-label font-medium capitalize transition-colors",
                    feedback === r ? "border-accent text-accent" : "border-line hover:text-ink"
                  )}
                >
                  {r.replace("_", " ")}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
