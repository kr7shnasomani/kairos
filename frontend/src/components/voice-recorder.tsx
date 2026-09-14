"use client";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui";

type State = "idle" | "recording" | "stopped";
const MAX_MB = 10;

interface Props {
  onBlob: (blob: Blob) => void;
  disabled?: boolean;
}

export function VoiceRecorder({ onBlob, disabled }: Props) {
  const [state, setState] = useState<State>("idle");
  const [seconds, setSeconds] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [denied, setDenied] = useState(false);
  const [tooLarge, setTooLarge] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current) clearInterval(timerRef.current);
      mediaRef.current?.stop();
    },
    [],
  );

  // One object URL per blob, revoked on replacement/unmount — avoids leaking a
  // blob: URL on every render (createObjectURL is not idempotent).
  useEffect(() => {
    if (!blob) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clearing the URL for an external Blob resource, not derived React state
      setAudioUrl(null);
      return;
    }
    const url = URL.createObjectURL(blob);
    // Defensive: an object URL is always a `blob:` URL. Refuse anything else before it
    // can reach the <audio src> sink, so no non-blob scheme can ever be rendered.
    setAudioUrl(url.startsWith("blob:") ? url : null);
    return () => URL.revokeObjectURL(url);
  }, [blob]);

  async function startRecording() {
    setDenied(false);
    setTooLarge(false);
    setBlob(null);
    setSeconds(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const b = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
        if (b.size > MAX_MB * 1024 * 1024) {
          setTooLarge(true);
          setState("idle");
          return;
        }
        setBlob(b);
        onBlob(b);
        setState("stopped");
      };
      mr.start(250);
      mediaRef.current = mr;
      setState("recording");
      timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
    } catch {
      setDenied(true);
    }
  }

  function acceptFile(f: File | undefined) {
    if (!f) return;
    if (f.size > MAX_MB * 1024 * 1024) {
      setTooLarge(true);
      return;
    }
    setTooLarge(false);
    setBlob(f);
    onBlob(f);
    setState("stopped");
  }

  function stopRecording() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    mediaRef.current?.stop();
    mediaRef.current = null;
  }

  function reset() {
    setState("idle");
    setBlob(null);
    setSeconds(0);
    setTooLarge(false);
  }

  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");

  if (denied) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-body text-muted">
          Microphone access denied. Upload an audio file instead.
        </p>
        <input
          type="file"
          accept="audio/*"
          aria-label="Upload audio recording"
          className="text-body text-ink"
          onChange={(e) => acceptFile(e.target.files?.[0])}
        />
        {tooLarge && (
          <p role="alert" className="text-body text-danger">Recording too large (max {MAX_MB} MB).</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4">
      {state === "idle" && (
        <button
          onClick={startRecording}
          disabled={disabled}
          aria-label="Start voice recording"
          className={cn(
            "grid size-16 place-items-center rounded-full transition-transform focus-visible:outline-2 focus-visible:outline-accent active:scale-95",
            disabled
              ? "cursor-not-allowed bg-line text-muted"
              : "bg-danger text-white hover:opacity-90",
          )}
        >
          <svg className="size-7" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 1a4 4 0 0 0-4 4v7a4 4 0 0 0 8 0V5a4 4 0 0 0-4-4z" />
            <path
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              d="M19 11a7 7 0 0 1-14 0M12 18v3M9 21h6"
            />
          </svg>
        </button>
      )}

      {/* A desktop without a microphone (or a browser that never answers the permission prompt) had
          no way to submit a note at all — the upload path only appeared after an explicit denial. */}
      {state === "idle" && (
        <label className={cn("text-caption text-accent underline", disabled ? "pointer-events-none opacity-50" : "cursor-pointer hover:no-underline")}>
          or upload an audio file
          <input
            type="file"
            accept="audio/*"
            aria-label="Upload audio recording"
            className="sr-only"
            disabled={disabled}
            onChange={(e) => acceptFile(e.target.files?.[0])}
          />
        </label>
      )}

      {state === "recording" && (
        <div className="flex flex-col items-center gap-3">
          <span
            className="tabular text-display font-semibold text-danger"
            aria-live="polite"
            aria-label={`Recording ${mm}:${ss}`}
          >
            {mm}:{ss}
          </span>
          <div className="size-3 animate-pulse rounded-full bg-danger" aria-hidden="true" />
          <button
            onClick={stopRecording}
            aria-label="Stop recording"
            className="grid size-14 place-items-center rounded-full border-4 border-danger bg-surface transition-transform focus-visible:outline-2 focus-visible:outline-accent active:scale-95"
          >
            <span className="size-5 rounded-sm bg-danger" aria-hidden="true" />
          </button>
          <span className="text-caption text-muted">Tap square to stop</span>
        </div>
      )}

      {state === "stopped" && blob && audioUrl && (
        <div className="flex w-full max-w-xs flex-col items-center gap-3">
          <audio
            controls
            src={audioUrl}
            className="w-full rounded-lg"
            aria-label="Playback of your recording"
          />
          <Button variant="ghost" onClick={reset}>
            Re-record
          </Button>
        </div>
      )}

      {tooLarge && (
        <p role="alert" className="text-body text-danger">
          Recording too large (max {MAX_MB} MB). Please record a shorter clip.
        </p>
      )}
    </div>
  );
}
