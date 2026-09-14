"use client";

// Voice-note capture deep-linked from a work order — transcribed and routed to quarantine.
import { useState } from "react";
import { useParams } from "next/navigation";
import { VoiceRecorder } from "@/components/voice-recorder";
import { submitVoiceNote } from "@/lib/api";
import { PageHeader } from "@/components/ui";
import { useMe } from "@/components/use-role";

type Stage = "record" | "submitting" | "done" | "error";

export default function VoicePage() {
  const { workOrderId } = useParams<{ workOrderId: string }>();
  const [stage, setStage] = useState<Stage>("record");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [duplicate, setDuplicate] = useState(false);
  const me = useMe();

  async function handleBlob(b: Blob) {
    setBlob(b);
  }

  async function submit() {
    if (!blob) return;
    setStage("submitting");
    try {
      // Attributed to the signed-in technician; a hardcoded "field_user" made every note anonymous in review.
      const res = await submitVoiceNote(workOrderId, blob, me?.email || me?.user_id || "field_user");
      setDuplicate(res.status === "duplicate");
      setTaskId(res.task_id ?? null);
      setStage("done");
    } catch {
      setStage("error");
    }
  }

  return (
    <div data-testid="work-order-voice-workspace" className="mx-auto max-w-[1100px]">
      <PageHeader
        compact
        className="mb-6"
        eyebrow={`Work order ${workOrderId}`}
        title="Voice note"
        lede="Record a field observation. Transcribed by Whisper and routed to the knowledge quarantine for engineering review."
      />

      <div data-testid="work-order-voice-layout" className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <main data-testid="work-order-voice-capture" className="min-w-0 rounded-2xl border border-line bg-surface p-4 shadow-sm sm:p-6">
      {stage === "record" && (
        <div className="flex flex-col items-center gap-6 py-8">
          <VoiceRecorder onBlob={handleBlob} />
          {blob && (
            <button
              onClick={submit}
              className="h-[52px] w-full rounded-xl bg-accent text-subtitle font-semibold text-on-accent transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-accent"
            >
              Submit for transcription
            </button>
          )}
        </div>
      )}

      {stage === "submitting" && (
        <div className="flex min-h-[200px] flex-col items-center justify-center gap-3">
          <span className="inline-flex gap-1.5">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="size-2 animate-bounce rounded-full bg-muted"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </span>
          <p className="text-body text-muted">Uploading…</p>
        </div>
      )}

      {stage === "done" && (
        <div className="flex flex-col items-center py-8 text-center">
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
          <h2 className="mt-4 text-title font-semibold">{duplicate ? "Already submitted" : "Submitted"}</h2>
          <p className="mt-2 text-body text-muted">
            {duplicate ? (
              "This exact recording is already in the knowledge quarantine, so it was not transcribed again."
            ) : (
              <>
                Transcription is processing.
                {taskId && (
                  <> Task <span className="tabular font-medium text-ink">{taskId}</span>.</>
                )}{" "}
                The result will appear in the knowledge quarantine once complete.
              </>
            )}
          </p>
        </div>
      )}

      {stage === "error" && (
        <div className="rounded-xl border border-[color-mix(in_srgb,var(--danger)_30%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_8%,transparent)] p-4 text-center">
          <p className="text-body font-semibold text-danger">Submission failed</p>
          <p className="mt-1 text-caption text-muted">
            Check your connection and try again.
          </p>
          <button
            onClick={() => setStage("record")}
            className="mt-3 min-h-11 rounded-lg border border-line px-4 py-2 text-body font-medium text-ink hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent"
          >
            Try again
          </button>
        </div>
      )}
        </main>

        <aside data-testid="work-order-voice-context" className="rounded-xl border border-line bg-surface p-4 shadow-sm lg:sticky lg:top-20">
          <p className="text-label font-bold uppercase tracking-[0.1em] text-accent">Work order</p>
          <p className="tabular mt-1 text-title font-semibold text-ink">{workOrderId}</p>
          <div className="mt-4 border-t border-line pt-4">
            <p className="text-label font-semibold text-ink">Quarantine route</p>
            <p className="mt-1.5 text-caption leading-relaxed text-muted">The transcription stays linked to this work order and requires engineering review before promotion.</p>
          </div>
          <p className="mt-4 rounded-lg bg-surface-2 p-3 text-caption text-muted">State the observed condition, location, and timing. Avoid assumptions about the cause.</p>
        </aside>
      </div>
    </div>
  );
}
