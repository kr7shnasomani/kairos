"use client";

import { useState } from "react";
import { VoiceRecorder } from "@/components/voice-recorder";
import { submitVoiceNote } from "@/lib/api";
import { PageHeader } from "@/components/ui";
import { useMe } from "@/components/use-role";

type Stage = "record" | "submitting" | "done" | "error";

// Ad-hoc voice capture reached from the field bottom-tab (no work order in the
// URL). The observation is tagged to an asset/work-order the worker types, then
// routed to the knowledge quarantine — same pipeline as the deep-linked page.
export default function VoiceCapturePage() {
  const [tag, setTag] = useState("");
  const [stage, setStage] = useState<Stage>("record");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [duplicate, setDuplicate] = useState(false);
  const me = useMe();

  async function submit() {
    if (!blob || !tag.trim()) return;
    setStage("submitting");
    try {
      // The reviewer sees "Submitted by" in quarantine; a hardcoded "field_user" made every note anonymous.
      const res = await submitVoiceNote(tag.trim(), blob, me?.email || me?.user_id || "field_user");
      setDuplicate(res.status === "duplicate");
      setTaskId(res.task_id ?? null);
      setStage("done");
    } catch {
      setStage("error");
    }
  }

  return (
    <div data-testid="field-voice-workspace" className="mx-auto max-w-[1100px]">
      <PageHeader
        compact
        className="mb-6"
        eyebrow="Field capture"
        title="Voice note"
        lede="Record a field observation. Transcribed by Whisper and routed to the knowledge quarantine for engineering review."
      />

      <div data-testid="field-voice-layout" className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <main data-testid="field-voice-capture" className="min-w-0 rounded-2xl border border-line bg-surface p-4 shadow-sm sm:p-6">
      {stage === "record" && (
        <div className="flex flex-col gap-5">
          <div>
            <label htmlFor="voice-tag" className="text-caption font-semibold text-ink">
              Asset / work-order tag <span className="text-danger">*</span>
            </label>
            <input
              id="voice-tag"
              value={tag}
              onChange={(e) => setTag(e.target.value)}
              placeholder="e.g. P-101 or WO-2024-118"
              className="mt-1.5 min-h-11 w-full rounded-xl border border-line bg-surface-2 px-3.5 text-subtitle text-ink placeholder:text-muted focus-visible:outline-2 focus-visible:outline-accent"
            />
          </div>

          <div className="flex flex-col items-center gap-6 py-4">
            <VoiceRecorder onBlob={setBlob} />
            {blob && (
              <button
                onClick={submit}
                disabled={!tag.trim()}
                className="h-[52px] w-full rounded-xl bg-accent text-subtitle font-semibold text-on-accent transition-opacity hover:opacity-90 disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-accent"
              >
                {tag.trim() ? "Submit for transcription" : "Enter a tag to submit"}
              </button>
            )}
          </div>
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
          {/* A duplicate used to read "Transcription is processing" — for a note that would never appear. */}
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
          <button
            onClick={() => { setStage("record"); setBlob(null); setTag(""); }}
            className="mt-4 min-h-11 rounded-lg border border-line px-4 py-2 text-body font-medium text-ink hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent"
          >
            Record another
          </button>
        </div>
      )}

      {stage === "error" && (
        <div className="rounded-xl border border-[color-mix(in_srgb,var(--danger)_30%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_8%,transparent)] p-4 text-center">
          <p className="text-body font-semibold text-danger">Submission failed</p>
          <p className="mt-1 text-caption text-muted">Check your connection and try again.</p>
          <button
            onClick={() => setStage("record")}
            className="mt-3 min-h-11 rounded-lg border border-line px-4 py-2 text-body font-medium text-ink hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent"
          >
            Try again
          </button>
        </div>
      )}
        </main>

        <aside data-testid="field-voice-context" className="rounded-xl border border-line bg-surface p-4 shadow-sm lg:sticky lg:top-20">
          <p className="text-label font-bold uppercase tracking-[0.1em] text-accent">Engineering review</p>
          <h2 className="mt-1 text-title font-semibold">From field note to governed fact</h2>
          <ol className="mt-4 space-y-3 text-caption text-muted">
            <li><span className="font-semibold text-ink">1. Capture</span><br />Record one clear observation and tag its asset or work order.</li>
            <li><span className="font-semibold text-ink">2. Transcribe</span><br />The recording is processed into reviewable text.</li>
            <li><span className="font-semibold text-ink">3. Quarantine</span><br />Engineering verifies it before it enters governed knowledge.</li>
          </ol>
        </aside>
      </div>
    </div>
  );
}
