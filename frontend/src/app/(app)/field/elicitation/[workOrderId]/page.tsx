"use client";

// Step-through elicitation questionnaire for a work order — answers feed the knowledge quarantine.
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getElicitationQuestions, submitElicitationResponses } from "@/lib/api";
import { enqueueWrite } from "@/lib/idb";
import type { ElicitationQuestion, ElicitationSession } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button, PageHeader } from "@/components/ui";

function QuestionCard({
  question,
  answer,
  onChange,
}: {
  question: ElicitationQuestion;
  answer: string;
  onChange: (v: string) => void;
}) {
  if (question.question_type === "multiple_choice" && question.options) {
    return (
      <div className="flex flex-col gap-2.5" role="group" aria-label={question.question_text}>
        {question.options.map((opt) => (
          <label
            key={opt}
            className={cn(
              "flex min-h-[56px] cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 text-sm transition-colors",
              answer === opt
                ? "border-accent bg-[color-mix(in_srgb,var(--accent)_8%,transparent)] font-semibold text-accent"
                : "border-line bg-surface hover:border-[color-mix(in_srgb,var(--accent)_35%,var(--line))]",
            )}
          >
            <input
              type="radio"
              name={`q-${question.question_id}`}
              value={opt}
              checked={answer === opt}
              onChange={() => onChange(opt)}
              className="sr-only"
            />
            <span
              className={cn(
                "grid size-5 shrink-0 place-items-center rounded-full border-2 transition-colors",
                answer === opt ? "border-accent bg-accent" : "border-line bg-surface",
              )}
              aria-hidden="true"
            >
              {answer === opt && <span className="size-2 rounded-full bg-on-accent" />}
            </span>
            {opt}
          </label>
        ))}
      </div>
    );
  }

  return (
    <textarea
      value={answer}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Describe your observation…"
      rows={5}
      aria-label={question.question_text}
      className="w-full resize-none rounded-xl border border-line bg-surface px-4 py-3 text-sm leading-relaxed outline-none transition-colors focus-visible:border-accent"
    />
  );
}

export default function ElicitationPage() {
  const { workOrderId } = useParams<{ workOrderId: string }>();
  const [session, setSession] = useState<ElicitationSession | null>(null);
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [queued, setQueued] = useState(false);

  useEffect(() => {
    let alive = true;
    getElicitationQuestions(workOrderId).then((r) => {
      if (!alive) return;
      // Live-only: no fixture questions. If none are ready, say so honestly.
      if (!r.data) { setFailed(true); return; }
      setFailed(false);
      setSession(r.data);
    }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [workOrderId, reload]);

  if (failed) {
    return (
      <div className="mx-auto max-w-lg px-5 py-16 text-center">
        <p className="text-subtitle font-semibold">No questions available</p>
        <p className="mt-1.5 text-body text-muted">This work order has no elicitation questions ready yet.</p>
        <button type="button" onClick={() => setReload((r) => r + 1)} className="mt-4 inline-flex min-h-11 items-center rounded-lg border border-line bg-surface-2 px-4 text-caption font-medium text-ink transition-colors hover:bg-canvas">Retry</button>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center" aria-label="Loading questions">
        <span className="inline-flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="size-2 animate-bounce rounded-full bg-muted"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </span>
      </div>
    );
  }

  const questions = session.questions;
  const current = questions[step]!;
  const isLast = step === questions.length - 1;
  const currentAnswer = answers[current.question_id] ?? "";

  async function advance() {
    if (!isLast) {
      setStep((s) => s + 1);
      return;
    }
    setSubmitting(true);
    // Positional + text, the shape the backend stores against the session's question list — also what
    // the offline queue replays, so a queued submission lands identically.
    const responses = questions
      .map((q, question_index) => ({ question_index, question: q.question_text, answer: answers[q.question_id] ?? "" }))
      .filter((r) => r.answer.trim());
    try {
      await submitElicitationResponses(workOrderId, responses);
      setSubmitted(true);
    } catch {
      // Offline — queue for replay
      await enqueueWrite(
        `/elicitation/${workOrderId}/responses`,
        "POST",
        { responses },
      ).catch(() => {});
      setQueued(true);
      setSubmitted(true);
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="mx-auto max-w-xl rounded-2xl border border-line bg-surface px-5 py-8 text-center shadow-sm sm:px-8">
        <div className="mx-auto grid size-14 place-items-center rounded-full bg-[color-mix(in_srgb,var(--verified)_12%,transparent)]">
          <svg
            className="size-7 text-verified"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </div>
        <h1 className="mt-4 text-title font-semibold">
          {queued ? "Responses queued" : "Responses submitted"}
        </h1>
        <p className="mt-2 text-body leading-relaxed text-muted">
          {queued
            ? "You're offline — responses saved locally and will sync automatically when connected."
            : "Your field observations entered the knowledge quarantine and will be reviewed by engineering authority."}
        </p>
      </div>
    );
  }

  return (
    <div data-testid="elicitation-workspace" className="mx-auto max-w-[1100px]">
      <PageHeader
        compact
        className="mb-6"
        eyebrow={`Work order ${workOrderId}`}
        title="Knowledge capture"
      />

      {/* Progress */}
      <div
        className="mb-5 flex items-center gap-2 rounded-xl border border-line bg-surface px-4 py-3 shadow-sm"
        role="progressbar"
        aria-valuenow={step + 1}
        aria-valuemin={1}
        aria-valuemax={questions.length}
        aria-label={`Question ${step + 1} of ${questions.length}`}
      >
        {questions.map((_, i) => (
          <span
            key={i}
            className={cn(
              "rounded-full transition-all",
              i === step
                ? "size-3 bg-accent"
                : i < step
                  ? "size-2 bg-verified"
                  : "size-2 bg-line",
            )}
          />
        ))}
        <span className="ml-1 text-caption text-muted">
          {step + 1} / {questions.length}
        </span>
      </div>

      <div data-testid="elicitation-layout" className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <main data-testid="elicitation-question" className="min-w-0 rounded-2xl border border-line bg-surface p-4 shadow-sm sm:p-6">
      <div className="min-h-[320px]">
        {current.context && (
          <div className="mb-4 rounded-lg border border-line bg-surface-2 px-3 py-2.5">
            <p className="text-caption leading-relaxed text-muted">
              <span className="font-semibold text-ink">Context: </span>
              {current.context}
            </p>
          </div>
        )}

        <h2 className="text-title font-semibold leading-snug">{current.question_text}</h2>

        <div className="mt-5">
          <QuestionCard
            question={current}
            answer={currentAnswer}
            onChange={(v) =>
              setAnswers((a) => ({ ...a, [current.question_id]: v }))
            }
          />
        </div>
      </div>

      <div className="mt-6 flex items-center gap-3">
        {step > 0 && (
          <Button
            variant="ghost"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={submitting}
            className="min-h-[52px] px-5 text-subtitle"
          >
            Back
          </Button>
        )}
        <Button
          variant="primary"
          onClick={advance}
          disabled={!currentAnswer.trim() || submitting}
          className="min-h-[52px] flex-1 text-subtitle"
        >
          {isLast
            ? submitting
              ? "Submitting…"
              : "Submit responses"
            : "Next →"}
        </Button>
      </div>
        </main>

        <aside data-testid="elicitation-context" className="rounded-xl border border-line bg-surface p-4 shadow-sm lg:sticky lg:top-20">
          <p className="text-label font-bold uppercase tracking-[0.1em] text-accent">Work order</p>
          <p className="tabular mt-1 text-title font-semibold">{workOrderId}</p>
          <div className="mt-4 border-t border-line pt-4">
            <p className="text-label font-semibold text-ink">Session progress</p>
            <p className="mt-1.5 text-caption text-muted">Question {step + 1} of {questions.length} · {Object.keys(answers).length} answered</p>
          </div>
          <div className="mt-4 border-t border-line pt-4">
            <p className="text-label font-semibold text-ink">Offline ready</p>
            <p className="mt-1.5 text-caption leading-relaxed text-muted">If the connection drops during submission, responses are queued locally and synced when connectivity returns.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}
