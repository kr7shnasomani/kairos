"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  getOffboarding,
  getOffboardingQuestions,
  submitOffboardingResponses,
} from "@/lib/api";
import type {
  OffboardingProgramme,
  OffboardingSessionItem,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button, StatusBadge } from "@/components/ui";
import { VoiceRecorder } from "@/components/voice-recorder";

// Session list panel — selects an item in-page (all items belong to one programme).
function SessionList({
  items,
  activeId,
  onSelect,
}: {
  items: OffboardingSessionItem[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <ol className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0">
      {items.map((s) => (
        <li key={s.id} className="shrink-0 lg:w-full">
          <button
            type="button"
            onClick={() => onSelect(s.id)}
            className={cn(
              "flex min-h-11 w-full min-w-48 items-center gap-3 rounded-lg px-3 py-2.5 text-left text-body transition-colors lg:min-w-0",
              s.id === activeId
                ? "bg-accent-soft font-semibold text-accent"
                : "text-muted hover:bg-surface-2 hover:text-ink",
            )}
          >
            <span className="tabular text-label">Session {s.session_number}</span>
            <span className="min-w-0 flex-1 truncate capitalize">{familyLabel(s.equipment_family)}</span>
            {s.status === "completed" ? (
              <svg className="size-3.5 shrink-0 text-verified" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-label="Completed">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            ) : s.status === "questions_ready" ? (
              <span className="size-1.5 shrink-0 rounded-full bg-accent" aria-label="Ready" />
            ) : (
              <span className="size-1.5 shrink-0 rounded-full bg-line" aria-label="Pending" />
            )}
          </button>
        </li>
      ))}
    </ol>
  );
}

// Interview panel for a questions_ready session item. Offboarding questions are
// positional free-text strings; answers are keyed by question index.
function Interview({
  programmeId,
  item,
  questions,
  onDone,
}: {
  programmeId: string;
  item: OffboardingSessionItem;
  questions: string[];
  onDone: () => void;
}) {
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [voiceAnswers, setVoiceAnswers] = useState<Record<number, boolean>>({});
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allAnswered = questions.every((_, i) => (answers[i] ?? "").trim());
  const answeredCount = questions.filter((_, i) => (answers[i] ?? "").trim()).length;
  const answeredPct = questions.length > 0 ? Math.round((answeredCount / questions.length) * 100) : 0;

  async function submit() {
    setSubmitting(true);
    setError(null);
    const responses = questions.map((_, i) => ({ question_index: i, answer: answers[i] ?? "" }));
    try {
      await submitOffboardingResponses(programmeId, item.id, responses);
      setSubmitted(true);
    } catch {
      setError("Responses were not saved. Check the connection and try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <div className="grid size-14 place-items-center rounded-full bg-[color-mix(in_srgb,var(--verified)_12%,transparent)]">
          <svg className="size-7 text-verified" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </div>
        <p className="text-subtitle font-semibold">Session complete</p>
        <p className="max-w-sm text-body text-muted">
          Responses entered the knowledge quarantine. Engineering will review and promote verified
          insights to the knowledge graph.
        </p>
        <Button variant="ghost" onClick={onDone}>Back to programme</Button>
      </div>
    );
  }

  return (
    <div data-testid="offboarding-interview" className="flex flex-col gap-6">
      <div className="rounded-xl border border-line bg-surface p-4 shadow-sm sm:p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-label font-bold uppercase tracking-[0.1em] text-accent">{familyLabel(item.equipment_family)}</p>
            <h2 className="mt-0.5 text-title font-semibold">Session {item.session_number} — expert interview</h2>
          </div>
          <span className="tabular text-caption font-medium text-muted">{answeredCount} of {questions.length} answered</span>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-line" aria-label={`${answeredPct}% answered`}>
          <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${answeredPct}%` }} />
        </div>
        <p className="mt-3 text-label text-muted">Responses enter knowledge quarantine for engineering review before promotion.</p>
      </div>

      <div className="flex flex-col gap-4">
        {questions.map((q, i) => (
          <div key={i} className="rounded-xl border border-line bg-surface p-4 shadow-sm sm:p-5">
            <p className="text-label font-bold uppercase tracking-[0.1em] text-muted">Question {i + 1} of {questions.length}</p>
            <p className="mt-1 text-subtitle font-semibold leading-snug">{q}</p>

            <div className="mt-3 flex flex-col gap-3">
              <textarea
                value={answers[i] ?? ""}
                onChange={(e) => setAnswers((a) => ({ ...a, [i]: e.target.value }))}
                placeholder="Describe your expert knowledge on this topic…"
                rows={3}
                aria-label={q}
                className="min-h-28 w-full resize-y rounded-lg border border-line bg-surface-2 px-3 py-2.5 text-body leading-relaxed outline-none focus-visible:border-accent"
              />
              {!voiceAnswers[i] ? (
                <button
                  type="button"
                  onClick={() => setVoiceAnswers((v) => ({ ...v, [i]: true }))}
                  className="inline-flex min-h-11 items-center gap-1.5 text-caption font-medium text-accent hover:underline focus-visible:outline-2 focus-visible:outline-accent sm:min-h-9"
                >
                  <svg className="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                    <path d="M12 1a4 4 0 0 0-4 4v7a4 4 0 0 0 8 0V5a4 4 0 0 0-4-4z" />
                    <path d="M19 11a7 7 0 0 1-14 0M12 18v3" />
                  </svg>
                  Use voice instead
                </button>
              ) : (
                <div>
                  {/* No off-boarding audio endpoint exists — the recording never leaves the
                      browser, so the UI must not claim it was attached. */}
                  <VoiceRecorder onBlob={() => {}} />
                  <p className="mt-1.5 text-caption text-muted">
                    Recording is a memory aid only — audio is not uploaded from off-boarding.
                    Type the key points into the answer above.
                  </p>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <Button variant="primary" onClick={submit} disabled={!allAnswered || submitting} className="mt-2 h-[48px] w-full">
        {submitting ? "Submitting…" : "Submit session responses"}
      </Button>
      {error && <p role="alert" className="text-body text-danger">{error}</p>}
    </div>
  );
}

export default function OffboardingSessionPage() {
  // The route folder is [sessionId], but the value is a *programme* id.
  const { sessionId: programmeId } = useParams<{ sessionId: string }>();
  const [programme, setProgramme] = useState<OffboardingProgramme | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [questionsByItem, setQuestionsByItem] = useState<Record<string, string[]>>({});
  const [failed, setFailed] = useState(false);
  const [selectedId, setSelectedId] = useState<string>("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let alive = true;
    getOffboarding(programmeId).then((r) => {
      if (!alive) return;
      // Live-only: no fixture stand-in for a real programme.
      if (!r.data) { setFailed(true); setLoaded(true); return; }
      setFailed(false);
      setProgramme(r.data);
      setLoaded(true);
    }).catch(() => { if (alive) { setFailed(true); setLoaded(true); } });
    getOffboardingQuestions(programmeId).then((r) => { if (alive) setQuestionsByItem(r.data); });
    return () => { alive = false; };
  }, [programmeId, refreshKey]);

  const items = useMemo(() => programme?.session_items ?? [], [programme]);

  // Derive the active session during render: honour an explicit selection, else
  // default to the first ready item, else the first item. (No setState-in-effect.)
  const activeId =
    selectedId && items.some((s) => s.id === selectedId)
      ? selectedId
      : (items.find((s) => s.status === "questions_ready") ?? items[0])?.id ?? "";
  const active = items.find((s) => s.id === activeId);
  const activeQuestions = active ? (questionsByItem[active.id] ?? []) : [];
  const completedSessions = items.filter((item) => item.status === "completed").length;
  const programmePct = items.length > 0 ? Math.round((completedSessions / items.length) * 100) : 0;

  if (!loaded) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center" aria-label="Loading">
        <span className="inline-flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <span key={i} className="size-2 animate-bounce rounded-full bg-muted" style={{ animationDelay: `${i * 0.15}s` }} />
          ))}
        </span>
      </div>
    );
  }

  if (failed) {
    return (
      <div className="mx-auto max-w-lg px-5 py-16 text-center">
        <p className="text-subtitle font-semibold">Couldn&apos;t load this programme</p>
        <p className="mt-1.5 text-body text-muted">Live data is unavailable right now.</p>
        <button type="button" onClick={() => { setFailed(false); setLoaded(false); setRefreshKey((k) => k + 1); }} className="mt-4 inline-flex min-h-11 items-center rounded-lg border border-line bg-surface-2 px-4 text-caption font-medium text-ink transition-colors hover:bg-canvas">Retry</button>
      </div>
    );
  }

  if (!programme) {
    return (
      <div className="mx-auto max-w-lg px-5 py-16 text-center">
        <p className="text-subtitle font-semibold">Programme not found</p>
        <p className="mt-1.5 text-body text-muted">
          This off-boarding programme doesn&apos;t exist or was cancelled.
        </p>
        <Link href="/offboarding" className="mt-4 inline-block text-body font-medium text-accent hover:underline">
          ← Back to programmes
        </Link>
      </div>
    );
  }

  return (
    <div data-testid="offboarding-session-workspace" className="mx-auto max-w-[1200px]">
      <div className="mb-4 flex items-center gap-2 text-body text-muted">
        <Link href="/offboarding" className="hover:text-ink focus-visible:outline-2 focus-visible:outline-accent">Offboarding</Link>
        <span aria-hidden="true">›</span>
        <span className="text-ink">{programme.personnel_email}</span>
      </div>

      <section data-testid="offboarding-profile-header" className="overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
        <div className="flex flex-wrap items-center gap-4 p-4 sm:p-5">
          <span className="tabular grid size-12 shrink-0 place-items-center rounded-full bg-accent-soft text-body font-bold text-accent">{emailInitials(programme.personnel_email)}</span>
          <div className="min-w-0 flex-1">
            <p className="text-label font-semibold uppercase tracking-[0.1em] text-accent">Expert handover</p>
            <h1 className="truncate text-subtitle font-semibold text-ink">{programme.personnel_email}</h1>
            <p className="mt-0.5 text-label text-muted">Retires {new Date(programme.retirement_date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</p>
          </div>
          <div className="min-w-40">
            <p className="tabular text-caption font-semibold text-ink">{completedSessions} of {items.length} sessions</p>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line"><div className="h-full rounded-full bg-accent transition-all" style={{ width: `${programmePct}%` }} /></div>
            <p className="tabular mt-1 text-right text-label text-muted">{programmePct}% captured</p>
          </div>
        </div>
      </section>

      <div className="mt-5 grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)] lg:items-start">
        <aside data-testid="offboarding-session-navigation" className="rounded-xl border border-line bg-surface p-3 shadow-sm lg:sticky lg:top-20">
          <p className="mb-2 px-2 text-label font-bold uppercase tracking-[0.1em] text-muted">Knowledge sessions</p>
          <SessionList items={items} activeId={activeId} onSelect={setSelectedId} />
        </aside>

        <div className="min-w-0">
          {!active ? (
            <p className="text-sm text-muted">No sessions in this programme yet.</p>
          ) : active.status === "questions_ready" && activeQuestions.length > 0 ? (
            <Interview
              key={active.id}
              programmeId={programmeId}
              item={active}
              questions={activeQuestions}
              onDone={() => setRefreshKey((k) => k + 1)}
            />
          ) : (
            <div className="rounded-xl border border-line bg-surface p-6">
              <p className="text-label font-bold uppercase tracking-[0.1em] text-muted">{familyLabel(active.equipment_family)}</p>
              <h2 className="mt-0.5 text-title font-semibold">Session {active.session_number}</h2>
              <p className="mt-1 text-body text-muted">
                Scheduled: {new Date(active.scheduled_for).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}
              </p>
              <div className="mt-4">
                {active.status === "pending" ? (
                  <StatusBadge tone="neutral">Pending — questions not yet generated</StatusBadge>
                ) : active.status === "completed" ? (
                  <StatusBadge tone="verified">Completed</StatusBadge>
                ) : (
                  <StatusBadge tone="info">Ready</StatusBadge>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Families created from asset classes are keys ("ROTATING_CENTRIFUGAL_PUMP"); show those as words and
 *  leave an already-readable name ("Control valves") untouched. */
function familyLabel(family: string) {
  return /^[A-Z0-9_-]+$/.test(family) ? family.replaceAll("_", " ").toLowerCase() : family;
}

function emailInitials(email: string) {
  const parts = email.split("@")[0].split(/[^a-z0-9]+/i).filter(Boolean);
  return (parts.length > 1 ? parts.map((part) => part[0]).join("") : parts[0]?.slice(0, 2) || "?").slice(0, 2).toUpperCase();
}
